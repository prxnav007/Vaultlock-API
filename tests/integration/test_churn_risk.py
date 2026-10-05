"""The churn-risk endpoint, against the real generated dataset.

These tests read the pipeline's database rather than the scratch test database,
because the point of the most important test here is to compare the endpoint's
answer with the stored training row for the same merchant and snapshot. Every
query is a SELECT; nothing is written.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from ml import config
from ml.features.definitions import FEATURE_NAMES_FULL

pytestmark = pytest.mark.db


def require_artifacts() -> dict:
    if not config.MODEL_PATH.exists() or not config.MODEL_METADATA_PATH.exists():
        pytest.skip("no trained model; run python -m ml.train")
    return json.loads(config.MODEL_METADATA_PATH.read_text())


@pytest.fixture(scope="module")
def metadata() -> dict:
    return require_artifacts()


@pytest.fixture(scope="module")
def exemplars() -> dict:
    if not config.EXEMPLARS_PATH.exists():
        pytest.skip("no exemplars; run python -m ml.explain")
    return json.loads(config.EXEMPLARS_PATH.read_text())


@pytest.fixture
async def client(metadata):
    """An ASGI client with the real app, including its lifespan."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c


async def score_exemplar(client, exemplar):
    """Score a pinned exemplar at its own snapshot.

    The default `as_of` is the end of the ledger, by which point a genuine
    churner has been silent for months and is correctly refused. An exemplar is
    defined at a particular snapshot, so that is the instant to ask about.
    """
    return await client.get(
        f"/merchants/{exemplar['merchant_id']}/churn-risk",
        params={"as_of": exemplar["snapshot_at"]},
    )


async def test_health_still_reports_ok(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_unknown_merchant_is_404(client) -> None:
    response = await client.get(f"/merchants/{uuid.uuid4()}/churn-risk")
    assert response.status_code == 404


async def test_response_matches_the_documented_shape(client, exemplars) -> None:
    merchant_id = exemplars["high_risk"]["merchant_id"]
    as_of = exemplars["high_risk"]["snapshot_at"]
    response = await client.get(
        f"/merchants/{merchant_id}/churn-risk", params={"as_of": as_of}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert set(body) == {
        "merchant_id",
        "snapshot_at",
        "churn_score",
        "risk_band",
        "predicted_churn",
        "top_factors",
        "model_version",
    }
    assert body["merchant_id"] == merchant_id
    assert 0.0 <= body["churn_score"] <= 1.0
    assert body["risk_band"] in {"LOW", "MEDIUM", "HIGH"}
    assert len(body["top_factors"]) == 3
    for factor in body["top_factors"]:
        assert factor["feature"] in FEATURE_NAMES_FULL
        assert factor["direction"] in {"increases_risk", "decreases_risk"}


async def test_predicted_churn_follows_the_frozen_threshold(
    client, exemplars, metadata
) -> None:
    threshold = metadata["classification_threshold"]
    for which in ("high_risk", "low_risk"):
        body = (await score_exemplar(client, exemplars[which])).json()
        assert body["predicted_churn"] == (body["churn_score"] >= threshold)


async def test_risk_band_agrees_with_the_recorded_edges(
    client, exemplars, metadata
) -> None:
    edges = metadata["risk_band_edges"]
    for which in ("high_risk", "low_risk"):
        body = (await score_exemplar(client, exemplars[which])).json()
        score = body["churn_score"]
        expected = (
            "HIGH"
            if score >= edges["high"]
            else "MEDIUM"
            if score >= edges["medium"]
            else "LOW"
        )
        assert body["risk_band"] == expected


async def test_as_of_defaults_to_the_end_of_the_ledger_not_now(
    client, exemplars
) -> None:
    """Scoring a fixed history at the wall clock would be meaningless.

    The dataset ends months before today, so a `now()` default would place every
    merchant far past their last attempt and report uniform maximal risk.
    """
    merchant_id = exemplars["low_risk"]["merchant_id"]
    body = (await client.get(f"/merchants/{merchant_id}/churn-risk")).json()
    snapshot = datetime.fromisoformat(body["snapshot_at"])
    assert snapshot < datetime.now(UTC)
    assert (datetime.now(UTC) - snapshot).days > 1


async def test_the_two_exemplars_are_ordered_as_the_report_claims(
    client, exemplars
) -> None:
    high = (await score_exemplar(client, exemplars["high_risk"])).json()
    low = (await score_exemplar(client, exemplars["low_risk"])).json()
    assert high["churn_score"] > low["churn_score"]


async def test_a_churned_merchant_is_refused_at_the_end_of_the_ledger(
    client, exemplars
) -> None:
    """The high-risk exemplar stopped paying long before the ledger ends.

    Asked about at the default `as_of`, it has no attempt in the prior 60 days
    and must be refused rather than scored -- it sits outside the population the
    model was fit on. The reason must say so, not claim the merchant never paid.
    """
    merchant_id = exemplars["high_risk"]["merchant_id"]
    response = await client.get(f"/merchants/{merchant_id}/churn-risk")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "insufficient_history"
    assert detail["reason"] == "no_recent_activity"
    # Never a score alongside a refusal.
    assert "churn_score" not in response.json()


async def test_the_same_merchant_is_scored_at_its_own_snapshot(
    client, exemplars
) -> None:
    """The refusal is about the instant asked about, not the merchant."""
    response = await score_exemplar(client, exemplars["high_risk"])
    assert response.status_code == 200
    assert response.json()["churn_score"] > 0.5


async def test_serving_features_equal_the_stored_training_row(client, exemplars) -> None:
    """The anti-drift test: one feature definition, two call paths.

    The endpoint builds features from SQL rows at request time; the parquet was
    built offline from array views. If these disagree, the model is being served
    inputs it was not trained on -- the exact failure the metadata contract can
    only detect after the fact.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.db.models import Merchant
    from app.services.churn_service import load_history
    from ml.features.definitions import compute_features

    snapshots = pd.read_parquet(config.SNAPSHOTS_PARQUET)
    engine = create_async_engine(settings.async_database_url)
    try:
        for which in ("high_risk", "low_risk"):
            merchant_id = exemplars[which]["merchant_id"]
            snapshot_at = pd.Timestamp(exemplars[which]["snapshot_at"])
            stored = snapshots[
                (snapshots["merchant_id"] == merchant_id)
                & (snapshots["snapshot_at"] == snapshot_at)
            ]
            assert len(stored) == 1, f"{which} not found in the snapshot table"
            stored_row = stored.iloc[0]

            async with AsyncSession(engine) as session:
                merchant = (
                    await session.execute(
                        select(Merchant).where(
                            Merchant.merchant_id == uuid.UUID(merchant_id)
                        )
                    )
                ).scalar_one()
                history = await load_history(
                    session, merchant, snapshot_at.to_pydatetime()
                )
            recomputed = compute_features(history, snapshot_at.timestamp())

            for feature in FEATURE_NAMES_FULL:
                offline, online = float(stored_row[feature]), recomputed[feature]
                if math.isnan(offline) or math.isnan(online):
                    assert math.isnan(offline) and math.isnan(online), feature
                else:
                    assert offline == pytest.approx(online, rel=1e-9), feature
    finally:
        await engine.dispose()
