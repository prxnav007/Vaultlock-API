"""The one and only definition of every V1 feature and of the churn label.

THE LABEL
---------
For a merchant and a snapshot time t:

    churn_next_60d = 1  if the merchant makes ZERO logical payment attempts
                        in the half-open interval (t, t + 60 days]
                     0  otherwise

"Attempt" means SUCCESS or FAILED alike. Churn here is the absence of
*attempts*, not the absence of successful payments: a merchant whose payments
keep failing is still showing up. Failure may predict departure, but failure
is not itself inactivity. The label is therefore a statement about future
behaviour, which is why it may read data after t and no feature ever may.

Both halves of the system import this module: the offline snapshot builder
(`ml.features.build_snapshots`) and the online churn-risk endpoint
(`app.services.churn_service`). There is deliberately no second, "vectorized"
implementation for training -- a second implementation is a second thing to
keep in step, and silent drift between training and serving features is the
failure mode the model-metadata contract exists to catch after the fact. One
implementation cannot drift from itself.

It is fast enough to be the only one because every window is two
`np.searchsorted` calls against a per-merchant sorted timestamp array, not a
mask over the full ledger: O(log n) per window instead of O(n).

Dependencies are stdlib + numpy on purpose. No pandas, no SQLAlchemy, no
xgboost -- so the request path can import it without pulling in the offline
stack, and the leakage tests can run with no database and no `[ml]` extra.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

SECONDS_PER_DAY = 86_400.0

# Pinned V1 constants. Also recorded in model_metadata.json so a saved model
# can never be served under different window semantics than it was trained on.
OBSERVATION_WINDOW_DAYS = 90
PREDICTION_HORIZON_DAYS = 60
SNAPSHOT_CADENCE_DAYS = 7
MIN_TENURE_DAYS = 90
RECENT_ACTIVITY_DAYS = 60

# Both SUCCESS and FAILED are merchant activity: a merchant whose payments keep
# failing is experiencing friction, not absence. Only terminal attempts can
# form a failure *rate*.
ACTIVITY_STATUSES = frozenset({"PENDING", "SUCCESS", "FAILED"})
TERMINAL_STATUSES = frozenset({"SUCCESS", "FAILED"})

RECENCY_FEATURES = ("recency_days",)
FREQUENCY_FEATURES = (
    "tx_count_30d",
    "tx_count_prev_30d",
    "tx_count_90d",
    "frequency_change",
)
MONETARY_FEATURES = (
    "avg_success_amount_30d",
    "avg_success_amount_prev_30d",
    "monetary_change",
)
FAILURE_FEATURES = (
    "failure_rate_30d",
    "failure_rate_prev_30d",
    "failure_rate_change",
)
TENURE_FEATURES = ("tenure_days",)

# Model C: recency, frequency, monetary, tenure. Model D adds reliability.
# The ablation that answers the project's research question is a change of
# feature list, not a fork of the training code.
FEATURE_NAMES_RFM = (
    *RECENCY_FEATURES,
    *FREQUENCY_FEATURES,
    *MONETARY_FEATURES,
    *TENURE_FEATURES,
)
FEATURE_NAMES_FULL = (
    *RECENCY_FEATURES,
    *FREQUENCY_FEATURES,
    *MONETARY_FEATURES,
    *FAILURE_FEATURES,
    *TENURE_FEATURES,
)

# Counts are never missing; anything that can be absent is a float carrying NaN.
INT_FEATURES = frozenset(FREQUENCY_FEATURES)


def to_epoch(value: datetime) -> float:
    """Timestamp as UTC epoch seconds. Naive input is rejected, not guessed."""
    if value.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value!r}")
    return value.timestamp()


@dataclass(frozen=True, slots=True)
class MerchantHistory:
    """One merchant's payment attempts, as parallel arrays sorted by time.

    `created_at` ascending is an invariant the window arithmetic depends on,
    so it is checked at construction rather than assumed.
    """

    merchant_id: str
    joined_at: float
    created_at: np.ndarray
    amount_minor: np.ndarray
    is_success: np.ndarray
    is_terminal: np.ndarray
    # True when this is a 90-day view and the merchant is known to have
    # transacted before it. The serving path fetches only the observation
    # window, so an empty array alone cannot distinguish a merchant who never
    # paid from one who has simply been dormant a long time. Both are
    # ineligible, but they are ineligible for different reasons, and a 409 that
    # reports "no payments" about a merchant with thousands of them is a lie.
    # The offline builder passes complete histories, so it leaves this False.
    earlier_activity: bool = False

    def __post_init__(self) -> None:
        n = self.created_at.size
        if not (
            self.amount_minor.size == n
            and self.is_success.size == n
            and self.is_terminal.size == n
        ):
            raise ValueError("history arrays must be the same length")
        if n > 1 and not np.all(np.diff(self.created_at) >= 0):
            raise ValueError("created_at must be sorted ascending")

    def __len__(self) -> int:
        return int(self.created_at.size)

    @classmethod
    def from_rows(
        cls,
        merchant_id: str,
        joined_at: datetime,
        rows: Iterable[tuple[datetime, int, str]],
        earlier_activity: bool = False,
    ) -> MerchantHistory:
        """Build from (created_at, amount_minor, status) rows.

        This is the constructor the API uses, straight off a result set. Set
        `earlier_activity` when the rows are a window and older payments exist.
        """
        ordered = sorted(rows, key=lambda row: row[0])
        statuses = [row[2] for row in ordered]
        return cls(
            merchant_id=merchant_id,
            joined_at=to_epoch(joined_at),
            created_at=np.array([to_epoch(r[0]) for r in ordered], dtype=np.float64),
            amount_minor=np.array([r[1] for r in ordered], dtype=np.int64),
            is_success=np.array([s == "SUCCESS" for s in statuses], dtype=bool),
            is_terminal=np.array([s in TERMINAL_STATUSES for s in statuses], dtype=bool),
            earlier_activity=earlier_activity,
        )

    @classmethod
    def from_arrays(
        cls,
        merchant_id: str,
        joined_at: float,
        created_at: np.ndarray,
        amount_minor: np.ndarray,
        is_success: np.ndarray,
        is_terminal: np.ndarray,
    ) -> MerchantHistory:
        """Build from pre-sorted array views -- no copying.

        The offline builder slices one contiguous block per merchant out of the
        full ledger and hands the views straight in.
        """
        return cls(
            merchant_id=merchant_id,
            joined_at=joined_at,
            created_at=created_at,
            amount_minor=amount_minor,
            is_success=is_success,
            is_terminal=is_terminal,
        )


# <listing:5.1>
def visible_cut(history: MerchantHistory, t: float) -> int:
    """Index one past the last payment visible at snapshot time t.

    Every feature reads `history.created_at[:cut]` and the arrays beside it,
    so a payment made after t is unreachable by construction rather than by
    convention. This is the single place leakage is prevented.
    """
    return int(np.searchsorted(history.created_at, t, side="right"))


def window(history: MerchantHistory, t: float, older: float, newer: float) -> slice:
    """Indices of attempts in the half-open interval (t - older, t - newer].

    Half-open on the left so adjacent windows -- 30d and prev_30d -- partition
    the past instead of double-counting the payment on their shared boundary.
    """
    lo = t - older * SECONDS_PER_DAY
    hi = t - newer * SECONDS_PER_DAY
    start = np.searchsorted(history.created_at, lo, side="right")
    stop = np.searchsorted(history.created_at, hi, side="right")
    return slice(int(start), int(stop))
# </listing:5.1>


def count_attempts(
    history: MerchantHistory, t: float, older: float, newer: float
) -> int:
    """Attempts in the window. SUCCESS and FAILED both count as activity."""
    span = window(history, t, older, newer)
    return span.stop - span.start


def recency_days(history: MerchantHistory, t: float) -> float:
    """Days since the most recent attempt visible at t.

    Clipped to the 90-day observation window: features may not see further
    back than that, so an empty window reports the window edge rather than an
    unbounded age. For training rows the clip never binds -- eligibility
    guarantees an attempt within 60 days -- so it introduces no train/serve
    skew, and it keeps a long-dormant merchant's score inside the range the
    model actually saw.
    """
    span = window(history, t, OBSERVATION_WINDOW_DAYS, 0.0)
    if span.stop == span.start:
        return float(OBSERVATION_WINDOW_DAYS)
    latest = history.created_at[span.stop - 1]
    return min((t - float(latest)) / SECONDS_PER_DAY, float(OBSERVATION_WINDOW_DAYS))


def tenure_days(history: MerchantHistory, t: float) -> float:
    """Days between joining the platform and the snapshot."""
    return (t - history.joined_at) / SECONDS_PER_DAY


def mean_success_amount(
    history: MerchantHistory, t: float, older: float, newer: float
) -> float:
    """Average amount over SUCCESS payments only, or NaN if there were none.

    Failed attempts are not completed payment volume, so they are excluded.
    An empty window yields NaN deliberately: inventing an average would tell
    the model a merchant transacted at zero value when in fact nothing is
    known, and XGBoost handles a genuine missing value natively.
    """
    span = window(history, t, older, newer)
    successes = history.is_success[span]
    if not successes.any():
        return float("nan")
    return float(history.amount_minor[span][successes].mean())


def failure_rate(
    history: MerchantHistory, t: float, older: float, newer: float
) -> float:
    """FAILED over terminal attempts in the window, or NaN if there were none.

    NaN rather than a zero-division guard, for the same reason as above: no
    terminal attempt means the rate is unknown, not that it is zero.
    """
    span = window(history, t, older, newer)
    terminal = history.is_terminal[span]
    n_terminal = int(terminal.sum())
    if n_terminal == 0:
        return float("nan")
    n_failed = n_terminal - int((terminal & history.is_success[span]).sum())
    return n_failed / n_terminal


def compute_features(history: MerchantHistory, t: float) -> dict[str, float]:
    """Every V1 feature at snapshot time t, keyed in FEATURE_NAMES_FULL order.

    Reads nothing after t. See `visible_cut` for why that is structural.
    """
    tx_30 = count_attempts(history, t, 30.0, 0.0)
    tx_prev_30 = count_attempts(history, t, 60.0, 30.0)
    amount_30 = mean_success_amount(history, t, 30.0, 0.0)
    amount_prev_30 = mean_success_amount(history, t, 60.0, 30.0)
    failure_30 = failure_rate(history, t, 30.0, 0.0)
    failure_prev_30 = failure_rate(history, t, 60.0, 30.0)
    return {
        "recency_days": recency_days(history, t),
        "tx_count_30d": float(tx_30),
        "tx_count_prev_30d": float(tx_prev_30),
        "tx_count_90d": float(count_attempts(history, t, 90.0, 0.0)),
        # A plain difference, not a boolean "is declining": the magnitude of
        # the fall is exactly the part that carries signal.
        "frequency_change": float(tx_30 - tx_prev_30),
        "avg_success_amount_30d": amount_30,
        "avg_success_amount_prev_30d": amount_prev_30,
        # NaN propagates through both changes, which is the intended behaviour.
        "monetary_change": amount_30 - amount_prev_30,
        "failure_rate_30d": failure_30,
        "failure_rate_prev_30d": failure_prev_30,
        "failure_rate_change": failure_30 - failure_prev_30,
        "tenure_days": tenure_days(history, t),
    }


def feature_vector(
    history: MerchantHistory, t: float, names: Sequence[str]
) -> np.ndarray:
    """Features as a row vector in the given order.

    The order comes from the model's own metadata at inference time, so a
    reordered feature list cannot silently produce a scored nonsense vector.
    """
    features = compute_features(history, t)
    return np.array([features[name] for name in names], dtype=np.float32)


# <listing:5.2>
def churn_next_60d(history: MerchantHistory, t: float) -> int:
    """1 if the merchant makes no payment attempt in (t, t + 60 days].

    This function reads the future on purpose -- it is the label. It is kept
    separate from `compute_features`, which must never call it, so that the
    only code touching data after t is the code whose job is to.
    """
    horizon_end = t + PREDICTION_HORIZON_DAYS * SECONDS_PER_DAY
    start = np.searchsorted(history.created_at, t, side="right")
    stop = np.searchsorted(history.created_at, horizon_end, side="right")
    return int(stop == start)
# </listing:5.2>


@dataclass(frozen=True, slots=True)
class Eligibility:
    ok: bool
    reason: str | None = None


def eligibility(
    history: MerchantHistory,
    t: float,
    dataset_end: float | None,
    *,
    mode: Literal["training", "inference"],
) -> Eligibility:
    """Whether merchant x t is a usable row, under training or serving rules.

    Spec section 26 gives three conditions: 90 days of tenure, 60 observable
    days after t, and at least one attempt in the prior 60 days. Both modes
    enforce conditions 1 and 3. The modes differ in exactly one respect:

    - Condition 2, "60 observable future days", applies only to training. At
      serving time t is the present, so there is no future to observe yet --
      that is the entire point of predicting.

    Condition 3 is enforced at serving as well, which means a merchant who has
    already been silent for 60 days is refused rather than scored. That is
    deliberate: the model was fit only on recently-active merchants, so such a
    merchant is outside the training distribution, and a confident-looking
    score there would be extrapolation dressed up as a measurement. The
    population the model speaks about is "merchants currently transacting", and
    the endpoint should decline to answer outside it.

    The practical consequence is that a merchant must be scored at a time when
    they were still active. For a fixed historical dataset that means passing
    `as_of` explicitly rather than relying on the end of the ledger.
    """
    cut = visible_cut(history, t)
    if cut == 0 and not history.earlier_activity:
        return Eligibility(False, "no_payments")
    if tenure_days(history, t) < MIN_TENURE_DAYS:
        return Eligibility(False, "tenure_lt_90d")
    if mode == "training":
        if dataset_end is None:
            raise ValueError("training eligibility needs dataset_end")
        if (dataset_end - t) / SECONDS_PER_DAY < PREDICTION_HORIZON_DAYS:
            return Eligibility(False, "horizon_unobservable")
    if count_attempts(history, t, RECENT_ACTIVITY_DAYS, 0.0) == 0:
        return Eligibility(False, "no_recent_activity")
    return Eligibility(True)
