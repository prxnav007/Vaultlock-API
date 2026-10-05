"""The generator must rebuild the same world from the same seed.

Reproducibility is the one property the synthetic dataset has to have: every
number in the report is downstream of it, so "we reran it and got different
figures" would invalidate the whole chapter. These tests need no database --
generation is pure, and the loading code lives in `ml.synthetic.load`.
"""
from dataclasses import replace
from datetime import UTC, date, datetime

import numpy as np
import pytest

from ml.features.definitions import TERMINAL_STATUSES
from ml.synthetic.generate import (
    GeneratorConfig,
    sample_profiles,
    simulate_merchant,
)

CFG = GeneratorConfig(n_merchants=40, months=24, end_date=date(2026, 6, 30), seed=42)
START = datetime(2024, 6, 30, tzinfo=UTC)


def simulate(cfg: GeneratorConfig):
    profiles = sample_profiles(cfg)
    return profiles, [simulate_merchant(p, cfg, START) for p in profiles]


def test_profiles_are_identical_across_runs() -> None:
    first, second = sample_profiles(CFG), sample_profiles(CFG)
    assert [p.merchant_id for p in first] == [p.merchant_id for p in second]
    assert [p.is_churner for p in first] == [p.is_churner for p in second]
    assert [p.churn_start_day for p in first] == [p.churn_start_day for p in second]
    assert [p.base_rate_per_day for p in first] == [
        p.base_rate_per_day for p in second
    ]


def test_payment_ids_are_identical_across_runs() -> None:
    """Primary keys are part of the dataset, so they must reproduce too."""
    _, first = simulate(CFG)
    _, second = simulate(CFG)
    assert [len(b) for b in first] == [len(b) for b in second]
    for a, b in zip(first, second, strict=True):
        assert a.payment_id == b.payment_id
        np.testing.assert_array_equal(a.created_at, b.created_at)
        np.testing.assert_array_equal(a.amount_minor, b.amount_minor)
        np.testing.assert_array_equal(a.status, b.status)
        np.testing.assert_array_equal(a.failure_code, b.failure_code)


def test_a_different_seed_produces_a_different_world() -> None:
    _, baseline = simulate(CFG)
    _, altered = simulate(replace(CFG, seed=43))
    assert [len(b) for b in baseline] != [len(b) for b in altered]


def test_a_smaller_run_is_a_prefix_of_a_larger_one() -> None:
    """Iterating on 20 merchants must describe the same 20 as a 40-merchant run.

    Every draw comes from a per-merchant stream keyed on the merchant's index,
    so growing the dataset appends merchants instead of reshuffling them.
    """
    small = sample_profiles(replace(CFG, n_merchants=20))
    large = sample_profiles(CFG)
    assert [p.merchant_id for p in small] == [p.merchant_id for p in large[:20]]


def test_all_uuids_are_distinct() -> None:
    profiles, batches = simulate(CFG)
    merchant_ids = {p.merchant_id for p in profiles}
    assert len(merchant_ids) == len(profiles)

    payment_ids = [pid for batch in batches for pid in batch.payment_id]
    assert len(set(payment_ids)) == len(payment_ids)
    assert merchant_ids.isdisjoint(payment_ids)


def test_uuids_are_version_4() -> None:
    for profile in sample_profiles(replace(CFG, n_merchants=5)):
        assert profile.merchant_id.version == 4


# --- Properties the spec requires of the generated world --------------------
def test_no_pending_payments_in_historical_data() -> None:
    """PENDING is a transient transport state, not merchant history."""
    _, batches = simulate(CFG)
    for batch in batches:
        assert set(np.unique(batch.status)) <= TERMINAL_STATUSES


def test_timestamps_are_sorted_within_each_merchant() -> None:
    """The feature core's window arithmetic depends on this ordering."""
    _, batches = simulate(CFG)
    for batch in batches:
        assert np.all(np.diff(batch.created_at) >= np.timedelta64(0, "us"))


def test_amounts_are_positive_integers() -> None:
    """The payments table's check constraint rejects anything else."""
    _, batches = simulate(CFG)
    for batch in batches:
        assert batch.amount_minor.dtype == np.int64
        assert (batch.amount_minor > 0).all()


def test_failure_codes_accompany_exactly_the_failed_attempts() -> None:
    _, batches = simulate(CFG)
    for batch in batches:
        failed = batch.status == "FAILED"
        has_code = np.array([code is not None for code in batch.failure_code])
        np.testing.assert_array_equal(failed, has_code)


def test_behaviour_is_heterogeneous_across_merchants() -> None:
    """A world where every merchant behaves alike would teach nothing."""
    _, batches = simulate(CFG)
    volumes = np.array([len(b) for b in batches], dtype=float)
    assert volumes.std() / volumes.mean() > 0.4


def test_churn_is_not_deterministic_from_the_latent_flag() -> None:
    """Churners must not be trivially separable by volume alone.

    If every churner were simply quieter overall, the prediction problem would
    be an identity check rather than a forecast.
    """
    profiles, batches = simulate(replace(CFG, n_merchants=300))
    volumes = np.array([len(b) for b in batches], dtype=float)
    churner = np.array([p.is_churner for p in profiles])
    if churner.sum() < 10:  # pragma: no cover - guards a degenerate draw
        pytest.skip("too few churners in this sample")
    # The distributions must overlap: some churners out-transact some actives.
    assert volumes[churner].max() > np.median(volumes[~churner])


def test_some_churners_keep_steady_payment_values() -> None:
    """Spec section 33: a declining amount must not be a churn tell."""
    profiles = sample_profiles(replace(CFG, n_merchants=400))
    churners = [p for p in profiles if p.is_churner]
    assert any(p.amount_trend >= 0 for p in churners)


def test_some_churners_have_no_rising_failure_rate() -> None:
    """Spec section 35: failures carry signal without revealing the label."""
    profiles = sample_profiles(replace(CFG, n_merchants=400))
    churners = [p for p in profiles if p.is_churner]
    assert any(not p.friction_rises_before_churn for p in churners)
    assert any(p.friction_rises_before_churn for p in churners)


def test_all_three_disengagement_modes_occur() -> None:
    profiles = sample_profiles(replace(CFG, n_merchants=400))
    modes = {p.churn_mode for p in profiles if p.is_churner}
    assert modes == {"gradual", "abrupt", "straggler"}
