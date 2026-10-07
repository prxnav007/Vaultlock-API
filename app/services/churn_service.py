"""Derive a merchant's current churn risk from the ledger.

The whole point of this module is that it computes features with the *same*
functions the training pipeline used -- `ml.features.definitions` -- rather than
with a serving-side reimplementation. The SQL below applies the same cut-off the
offline builder applies in numpy, and a test asserts the resulting vector equals
the stored training row for the same merchant and snapshot.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Merchant, Payment
from app.schemas.analytics import ChurnRiskResponse, TopFactor
from ml.features.definitions import (
    MerchantHistory,
    OBSERVATION_WINDOW_DAYS,
    compute_features,
    eligibility,
    feature_vector,
)
from ml.inference import ChurnModel

TOP_FACTOR_COUNT = 3


class MerchantNotFound(Exception):
    pass


class InsufficientHistory(Exception):
    """The merchant exists but cannot be scored, with the unmet condition."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def latest_ledger_time(session: AsyncSession) -> datetime | None:
    """The most recent payment in the whole ledger.

    This is the default `as_of`, not the wall clock. The dataset is a fixed
    history, so scoring at `now()` would place every merchant months past their
    last attempt and report uniformly maximal risk -- an artefact of the clock
    rather than a finding about the merchants.
    """
    result = await session.execute(select(func.max(Payment.created_at)))
    return result.scalar_one_or_none()


async def load_history(
    session: AsyncSession, merchant: Merchant, as_of: datetime
) -> MerchantHistory:
    """Fetch the observable window of a merchant's attempts.

    `created_at <= as_of` is the online twin of the offline `visible_cut`: the
    leakage boundary is enforced in SQL here and in numpy there, and the two
    must read the same.
    """
    window_start = as_of - timedelta(days=OBSERVATION_WINDOW_DAYS)
    result = await session.execute(
        select(Payment.created_at, Payment.amount_minor, Payment.status)
        .where(
            Payment.merchant_id == merchant.merchant_id,
            Payment.created_at > window_start,
            Payment.created_at <= as_of,
        )
        .order_by(Payment.created_at)
    )
    rows = [
        (created_at, amount, status.value)
        for created_at, amount, status in result.all()
    ]
    earlier_activity = False
    if not rows:
        # An empty window says nothing about whether this merchant ever paid.
        # Both cases are ineligible, but they are different refusals, and
        # reporting "no payments" about a merchant with thousands of old ones
        # would misdescribe why the request failed.
        ever = await session.execute(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.merchant_id == merchant.merchant_id,
                Payment.created_at <= as_of,
            )
        )
        earlier_activity = ever.scalar_one() > 0

    return MerchantHistory.from_rows(
        merchant_id=str(merchant.merchant_id),
        joined_at=merchant.joined_at,
        rows=rows,
        earlier_activity=earlier_activity,
    )


def top_factors(
    contributions: np.ndarray, feature_names: tuple[str, ...], k: int = TOP_FACTOR_COUNT
) -> list[TopFactor]:
    """The k features that moved this prediction most, with their direction."""
    order = np.argsort(np.abs(contributions))[::-1][:k]
    return [
        TopFactor(
            feature=feature_names[i],
            direction="increases_risk" if contributions[i] > 0 else "decreases_risk",
        )
        for i in order
    ]


async def churn_risk(
    session: AsyncSession,
    model: ChurnModel,
    merchant_id: uuid.UUID,
    as_of: datetime | None = None,
) -> ChurnRiskResponse:
    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        raise MerchantNotFound(str(merchant_id))

    if as_of is None:
        as_of = await latest_ledger_time(session) or datetime.now(UTC)
    if as_of.tzinfo is None:
        # A bare `?as_of=2026-04-26` parses to a naive datetime, and astimezone
        # would read it as server-local time -- so the same query would pick a
        # different snapshot on a machine in a different timezone. The ledger is
        # stored in UTC, so a caller who omitted an offset meant UTC.
        as_of = as_of.replace(tzinfo=UTC)
    as_of = as_of.astimezone(UTC).replace(microsecond=0)

    history = await load_history(session, merchant, as_of)
    snapshot = as_of.timestamp()

    # Serving rules: tenure and recent activity are both required, so a
    # merchant already silent for 60 days is refused rather than scored outside
    # the distribution the model was fit on. Only the "observable future"
    # condition is dropped, since at serving time there is no future yet.
    verdict = eligibility(history, snapshot, None, mode="inference")
    if not verdict.ok:
        raise InsufficientHistory(verdict.reason or "ineligible")

    features = feature_vector(history, snapshot, model.feature_names)
    score = model.score(features)
    contributions, _base = model.contributions(features)

    return ChurnRiskResponse(
        merchant_id=merchant.merchant_id,
        snapshot_at=as_of,
        churn_score=score,
        risk_band=model.risk_band(score),
        predicted_churn=model.predicted_churn(score),
        top_factors=top_factors(contributions, model.feature_names),
        model_version=model.metadata.model_version,
    )


async def recent_activity(
    session: AsyncSession, merchant_id: uuid.UUID, as_of: datetime, weeks: int = 12
) -> list[dict]:
    """Weekly attempt counts, for the demonstration dashboard's activity chart.

    Derived from the same `payments` rows the features use, so the chart and the
    score can never describe different histories.
    """
    window_start = as_of - timedelta(weeks=weeks)
    result = await session.execute(
        select(Payment.created_at, Payment.status)
        .where(
            Payment.merchant_id == merchant_id,
            Payment.created_at > window_start,
            Payment.created_at <= as_of,
        )
        .order_by(Payment.created_at)
    )
    buckets: dict[int, dict[str, int]] = {
        week: {"attempts": 0, "failures": 0} for week in range(weeks)
    }
    for created_at, status in result.all():
        index = int((as_of - created_at).days // 7)
        if 0 <= index < weeks:
            buckets[index]["attempts"] += 1
            if status.value == "FAILED":
                buckets[index]["failures"] += 1
    return [
        {
            "weeks_ago": week,
            "attempts": buckets[week]["attempts"],
            "failures": buckets[week]["failures"],
        }
        for week in sorted(buckets, reverse=True)
    ]


def features_for_display(history: MerchantHistory, snapshot: float) -> dict[str, float]:
    """Every computed feature, for the dashboard's detail panel."""
    return compute_features(history, snapshot)
