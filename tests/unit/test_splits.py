"""Chronological splits and their purge gaps.

The purge gap is the subtle part. Because a label looks 60 days forward, a
training row dated just before the validation period describes an outcome that
overlaps validation decision points. Without a gap wider than the horizon, the
model is scored on a future it was partly trained on.
"""
import pandas as pd
import pytest

from ml.features.definitions import PREDICTION_HORIZON_DAYS
from ml.splits import apply, plan_splits, to_dict

WEEKS = [pd.Timestamp("2024-09-29", tz="UTC") + pd.Timedelta(weeks=i) for i in range(83)]


def test_splits_are_ordered_in_time() -> None:
    plan = plan_splits(WEEKS)
    assert plan.train.end < plan.valid.start
    assert plan.valid.end < plan.test.start


def test_purge_gap_covers_the_label_horizon() -> None:
    plan = plan_splits(WEEKS)
    assert plan.purge_days >= PREDICTION_HORIZON_DAYS
    for earlier, later in ((plan.train, plan.valid), (plan.valid, plan.test)):
        gap_days = (later.start - earlier.end).days
        assert gap_days > PREDICTION_HORIZON_DAYS


def test_a_purge_narrower_than_the_horizon_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not cover"):
        plan_splits(WEEKS, purge_weeks=8)  # 56 days < 60


def test_every_week_is_used_exactly_once() -> None:
    plan = plan_splits(WEEKS)
    covered = [
        week
        for split in (plan.train, plan.gap1, plan.valid, plan.gap2, plan.test)
        for week in split.weeks
    ]
    assert sorted(covered) == WEEKS
    assert len(set(covered)) == len(WEEKS)


def test_too_few_weeks_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least"):
        plan_splits(WEEKS[:20])


def test_validation_and_test_sizes_are_fixed_from_the_end() -> None:
    """Training absorbs extra history; the evaluation periods stay put."""
    short = plan_splits(WEEKS[:70])
    long = plan_splits(WEEKS)
    assert short.test.n_weeks == long.test.n_weeks
    assert short.valid.n_weeks == long.valid.n_weeks
    assert long.train.n_weeks > short.train.n_weeks
    assert short.test.end == WEEKS[69]
    assert long.test.end == WEEKS[-1]


def test_apply_partitions_rows_without_overlap() -> None:
    frame = pd.DataFrame(
        {
            "snapshot_at": WEEKS * 2,
            "merchant_id": [f"m{i}" for i in range(len(WEEKS) * 2)],
            "churn_next_60d": [i % 2 for i in range(len(WEEKS) * 2)],
        }
    )
    plan = plan_splits(WEEKS)
    parts = apply(frame, plan)

    assert set(parts) == {"train", "validation", "test"}
    total = sum(len(part) for part in parts.values())
    # The purge-gap rows are deliberately dropped, not assigned anywhere.
    assert total < len(frame)
    ids = [mid for part in parts.values() for mid in part["merchant_id"]]
    assert len(ids) == len(set(ids))

    for name, part in parts.items():
        weeks = set(part["snapshot_at"])
        for other_name, other in parts.items():
            if other_name != name:
                assert weeks.isdisjoint(set(other["snapshot_at"]))


def test_to_dict_records_the_boundaries() -> None:
    frame = pd.DataFrame(
        {
            "snapshot_at": WEEKS,
            "churn_next_60d": [0] * len(WEEKS),
        }
    )
    plan = plan_splits(WEEKS)
    described = to_dict(frame, plan)

    assert described["purge_gap_days"] == plan.purge_days
    assert {"train", "validation", "test"} <= set(described["splits"])
    for key in ("train", "validation", "test"):
        entry = described["splits"][key]
        assert entry["weeks"] > 0
        assert entry["start"] <= entry["end"]
