"""The six leakage proofs spec Milestone 4 requires, plus the NaN contract.

These run with no database and no `[ml]` extra: the feature core is a
numpy-only leaf module, and keeping its tests that cheap is what makes it
reasonable to re-run them on every change.
"""
import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from ml.features.definitions import (
    FEATURE_NAMES_FULL,
    FEATURE_NAMES_RFM,
    MerchantHistory,
    OBSERVATION_WINDOW_DAYS,
    SECONDS_PER_DAY,
    churn_next_60d,
    compute_features,
    eligibility,
    feature_vector,
)

T0 = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
SNAPSHOT = T0.timestamp()


def history(
    *offsets_days: float,
    joined_days_ago: float = 400.0,
    statuses: list[str] | None = None,
    amounts: list[int] | None = None,
) -> MerchantHistory:
    """A history whose payments sit at the given day offsets relative to T0.

    Negative offsets are in the past, positive in the future.
    """
    rows = []
    for i, offset in enumerate(offsets_days):
        when = T0 + timedelta(seconds=offset * SECONDS_PER_DAY)
        status = statuses[i] if statuses else "SUCCESS"
        amount = amounts[i] if amounts else 10_000
        rows.append((when, amount, status))
    return MerchantHistory.from_rows(
        "m1", T0 - timedelta(days=joined_days_ago), rows
    )


def same_features(a: dict[str, float], b: dict[str, float]) -> bool:
    """Equality that treats NaN as equal to NaN."""
    assert a.keys() == b.keys()
    return all(
        (math.isnan(a[k]) and math.isnan(b[k])) or a[k] == b[k] for k in a
    )


# --- Proof 1: a payment after the snapshot cannot change any feature --------
@pytest.mark.parametrize("future_offset", [1 / 86400, 0.5, 1.0, 59.0, 200.0])
def test_payment_after_snapshot_does_not_change_features(future_offset) -> None:
    before = history(-50.0, -20.0, -5.0)
    after = history(-50.0, -20.0, -5.0, future_offset)
    assert same_features(
        compute_features(before, SNAPSHOT), compute_features(after, SNAPSHOT)
    )


# --- Proof 2: future data moves the label, never the features --------------
def test_future_payment_changes_label_not_features() -> None:
    quiet = history(-50.0, -20.0, -5.0)
    active = history(-50.0, -20.0, -5.0, 30.0)

    assert churn_next_60d(quiet, SNAPSHOT) == 1
    assert churn_next_60d(active, SNAPSHOT) == 0
    assert same_features(
        compute_features(quiet, SNAPSHOT), compute_features(active, SNAPSHOT)
    )


# --- Proof 3: FAILED attempts are activity ---------------------------------
def test_failed_attempts_count_as_activity() -> None:
    failed_only = history(
        -40.0, -10.0, 15.0, statuses=["FAILED", "FAILED", "FAILED"]
    )
    features = compute_features(failed_only, SNAPSHOT)

    # Activity in the horizon, even though nothing succeeded.
    assert churn_next_60d(failed_only, SNAPSHOT) == 0
    assert features["tx_count_30d"] == 1
    assert features["recency_days"] == pytest.approx(10.0)
    # ...but failed attempts are not completed payment volume.
    assert math.isnan(features["avg_success_amount_30d"])
    assert features["failure_rate_30d"] == 1.0


# --- Proof 4: window boundaries are half-open ------------------------------
def test_payment_exactly_at_snapshot_is_visible() -> None:
    features = compute_features(history(0.0), SNAPSHOT)
    assert features["tx_count_30d"] == 1
    assert features["recency_days"] == 0.0


def test_shared_boundary_belongs_to_the_older_window() -> None:
    """A payment exactly 30 days old is in prev_30d, not in 30d.

    Adjacent windows must partition the past; counting it twice would inflate
    tx_count and silently zero out frequency_change.
    """
    features = compute_features(history(-30.0), SNAPSHOT)
    assert features["tx_count_30d"] == 0
    assert features["tx_count_prev_30d"] == 1
    assert features["frequency_change"] == -1


def test_observation_window_excludes_its_far_edge() -> None:
    assert compute_features(history(-90.0), SNAPSHOT)["tx_count_90d"] == 0
    assert compute_features(history(-89.9), SNAPSHOT)["tx_count_90d"] == 1


def test_horizon_includes_its_far_edge() -> None:
    """The label window is (t, t + 60d], so day 60 exactly is still activity."""
    assert churn_next_60d(history(-1.0, 60.0), SNAPSHOT) == 0
    assert churn_next_60d(history(-1.0, 60.1), SNAPSHOT) == 1


# --- Proof 5: empty windows preserve NaN, never divide by zero -------------
def test_missing_monetary_window_is_nan_not_zero() -> None:
    # Activity in both windows, but every attempt failed.
    hist = history(-40.0, -10.0, statuses=["FAILED", "FAILED"])
    with np.errstate(all="raise"):
        features = compute_features(hist, SNAPSHOT)

    assert math.isnan(features["avg_success_amount_30d"])
    assert math.isnan(features["avg_success_amount_prev_30d"])
    assert math.isnan(features["monetary_change"])


def test_missing_failure_window_is_nan_not_zero() -> None:
    # No terminal attempt in prev_30d at all, so the rate is unknown there.
    hist = history(-10.0, statuses=["SUCCESS"])
    with np.errstate(all="raise"):
        features = compute_features(hist, SNAPSHOT)

    assert features["failure_rate_30d"] == 0.0
    assert math.isnan(features["failure_rate_prev_30d"])
    assert math.isnan(features["failure_rate_change"])


def test_empty_history_produces_no_warnings_and_clipped_recency() -> None:
    with np.errstate(all="raise"):
        features = compute_features(history(), SNAPSHOT)
    assert features["recency_days"] == float(OBSERVATION_WINDOW_DAYS)
    assert features["tx_count_90d"] == 0


def test_recency_is_clipped_to_the_observation_window() -> None:
    """A payment older than 90 days reports the window edge, not its true age."""
    assert compute_features(history(-300.0), SNAPSHOT)["recency_days"] == 90.0


# --- Proof 6: eligibility rules -------------------------------------------
DATASET_END = (T0 + timedelta(days=90)).timestamp()


def test_tenure_under_90_days_is_ineligible() -> None:
    hist = history(-5.0, joined_days_ago=89.0)
    verdict = eligibility(hist, SNAPSHOT, DATASET_END, mode="training")
    assert (verdict.ok, verdict.reason) == (False, "tenure_lt_90d")


def test_unobservable_horizon_is_ineligible_for_training() -> None:
    near_end = (T0 + timedelta(days=59)).timestamp()
    verdict = eligibility(history(-5.0), SNAPSHOT, near_end, mode="training")
    assert (verdict.ok, verdict.reason) == (False, "horizon_unobservable")


def test_no_recent_activity_is_ineligible_for_training() -> None:
    verdict = eligibility(history(-61.0), SNAPSHOT, DATASET_END, mode="training")
    assert (verdict.ok, verdict.reason) == (False, "no_recent_activity")


def test_eligible_training_row() -> None:
    assert eligibility(history(-5.0), SNAPSHOT, DATASET_END, mode="training").ok


def test_a_merchant_with_no_payments_is_ineligible_in_both_modes() -> None:
    empty = history()
    for mode in ("training", "inference"):
        verdict = eligibility(empty, SNAPSHOT, DATASET_END, mode=mode)
        assert (verdict.ok, verdict.reason) == (False, "no_payments")


def test_a_dormant_merchant_is_refused_at_serving_too() -> None:
    """Recent activity is required in both modes.

    The model was fit only on currently-transacting merchants, so scoring one
    that went silent 80 days ago would be extrapolation presented as a
    measurement. The endpoint declines instead.
    """
    dormant = history(-80.0)
    for mode, end in (("training", DATASET_END), ("inference", None)):
        verdict = eligibility(dormant, SNAPSHOT, end, mode=mode)
        assert (verdict.ok, verdict.reason) == (False, "no_recent_activity")


def test_inference_drops_only_the_observable_horizon_condition() -> None:
    """The single intended difference between the two modes."""
    active = history(-5.0)
    near_end = (T0 + timedelta(days=10)).timestamp()
    assert not eligibility(active, SNAPSHOT, near_end, mode="training").ok
    assert eligibility(active, SNAPSHOT, None, mode="inference").ok


def test_a_windowed_history_reports_dormancy_not_absence() -> None:
    """The 409 reason must describe the real situation.

    The serving path fetches only 90 days, so a merchant dormant longer than
    that arrives with an empty array. Without `earlier_activity` that is
    indistinguishable from never having paid, and the API would report
    "no_payments" about a merchant with thousands of them.
    """
    windowed = MerchantHistory.from_rows("m1", T0 - timedelta(days=400), [], True)
    verdict = eligibility(windowed, SNAPSHOT, None, mode="inference")
    assert (verdict.ok, verdict.reason) == (False, "no_recent_activity")

    never_paid = MerchantHistory.from_rows("m1", T0 - timedelta(days=400), [])
    verdict = eligibility(never_paid, SNAPSHOT, None, mode="inference")
    assert (verdict.ok, verdict.reason) == (False, "no_payments")


# --- Contract checks ------------------------------------------------------
def test_feature_names_match_computed_keys() -> None:
    assert tuple(compute_features(history(-5.0), SNAPSHOT)) == FEATURE_NAMES_FULL


def test_rfm_set_is_the_full_set_without_failure_features() -> None:
    assert set(FEATURE_NAMES_RFM) < set(FEATURE_NAMES_FULL)
    assert set(FEATURE_NAMES_FULL) - set(FEATURE_NAMES_RFM) == {
        "failure_rate_30d",
        "failure_rate_prev_30d",
        "failure_rate_change",
    }


def test_identifiers_are_not_features() -> None:
    """merchant_id and snapshot_at are metadata; feeding either is leakage."""
    assert "merchant_id" not in FEATURE_NAMES_FULL
    assert "snapshot_at" not in FEATURE_NAMES_FULL


def test_feature_vector_follows_the_requested_order() -> None:
    hist = history(-40.0, -10.0)
    reversed_names = tuple(reversed(FEATURE_NAMES_FULL))
    forward = feature_vector(hist, SNAPSHOT, FEATURE_NAMES_FULL)
    backward = feature_vector(hist, SNAPSHOT, reversed_names)
    assert forward.dtype == np.float32
    np.testing.assert_array_equal(forward, backward[::-1])


def test_unsorted_history_is_rejected() -> None:
    with pytest.raises(ValueError, match="sorted"):
        MerchantHistory.from_arrays(
            "m1",
            0.0,
            np.array([10.0, 5.0]),
            np.array([1, 1]),
            np.array([True, True]),
            np.array([True, True]),
        )


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MerchantHistory.from_rows("m1", datetime(2026, 1, 1), [])
