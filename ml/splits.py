"""Chronological train/validation/test splits with purge gaps.

A random shuffle is forbidden here. Because the label looks 60 days forward, a
shuffled split would put a merchant's later snapshots in training and its
earlier ones in test, letting the model learn from the very future it is being
asked to predict. Splits are therefore cut by snapshot date, and separated by
gaps wider than the horizon so no training row's label window reaches into a
validation or test decision point.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from ml import config
from ml.features.definitions import PREDICTION_HORIZON_DAYS


@dataclass(frozen=True, slots=True)
class Split:
    name: str
    weeks: tuple[pd.Timestamp, ...]

    @property
    def start(self) -> pd.Timestamp:
        return self.weeks[0]

    @property
    def end(self) -> pd.Timestamp:
        return self.weeks[-1]

    @property
    def n_weeks(self) -> int:
        return len(self.weeks)

    def label(self) -> str:
        return f"{self.start.date()} to {self.end.date()}"


@dataclass(frozen=True, slots=True)
class SplitPlan:
    train: Split
    gap1: Split
    valid: Split
    gap2: Split
    test: Split
    purge_days: int

    def modelling(self) -> tuple[Split, Split, Split]:
        return self.train, self.valid, self.test


def plan_splits(
    weeks: Sequence[pd.Timestamp],
    purge_weeks: int = config.PURGE_WEEKS,
    valid_weeks: int = config.VALID_WEEKS,
    test_weeks: int = config.TEST_WEEKS,
) -> SplitPlan:
    """Allocate splits backwards from the most recent snapshot week.

    Working backwards keeps validation and test at fixed sizes and lets
    training absorb whatever history remains, rather than letting the test
    period shrink as the dataset grows.
    """
    if purge_weeks * 7 < PREDICTION_HORIZON_DAYS:
        raise ValueError(
            f"purge of {purge_weeks} weeks does not cover the "
            f"{PREDICTION_HORIZON_DAYS}-day label horizon"
        )
    needed = test_weeks + purge_weeks + valid_weeks + purge_weeks + 1
    if len(weeks) < needed:
        raise ValueError(f"need at least {needed} snapshot weeks, got {len(weeks)}")

    ordered = list(weeks)
    test = ordered[-test_weeks:]
    gap2 = ordered[-(test_weeks + purge_weeks) : -test_weeks]
    valid_end = -(test_weeks + purge_weeks)
    valid = ordered[valid_end - valid_weeks : valid_end]
    gap1_end = valid_end - valid_weeks
    gap1 = ordered[gap1_end - purge_weeks : gap1_end]
    train = ordered[: gap1_end - purge_weeks]

    plan = SplitPlan(
        train=Split("train", tuple(train)),
        gap1=Split("purge gap", tuple(gap1)),
        valid=Split("validation", tuple(valid)),
        gap2=Split("purge gap", tuple(gap2)),
        test=Split("test", tuple(test)),
        purge_days=purge_weeks * 7,
    )
    assert plan.train.end < plan.valid.start < plan.test.start
    covered = [w for split in (train, gap1, valid, gap2, test) for w in split]
    assert len(covered) == len(set(covered)) == len(ordered)
    return plan


def apply(frame: pd.DataFrame, plan: SplitPlan) -> dict[str, pd.DataFrame]:
    """Partition the snapshot table by split."""
    return {
        split.name: frame[frame["snapshot_at"].isin(split.weeks)]
        for split in plan.modelling()
    }


def describe(frame: pd.DataFrame, plan: SplitPlan) -> str:
    """The split table, printed because the spec requires the boundaries shown."""
    lines = [
        f"{'split':<12} {'snapshot dates':<26} {'weeks':>5} {'rows':>8} "
        f"{'pos':>6} {'rate':>7}",
    ]
    for split in (plan.train, plan.gap1, plan.valid, plan.gap2, plan.test):
        rows = frame[frame["snapshot_at"].isin(split.weeks)]
        if split.name == "purge gap":
            lines.append(
                f"{'(purge gap)':<12} {split.label():<26} {split.n_weeks:>5} "
                f"{'-':>8} {'-':>6} {'-':>7}"
            )
            continue
        positives = int(rows["churn_next_60d"].sum())
        rate = positives / len(rows) if len(rows) else 0.0
        lines.append(
            f"{split.name:<12} {split.label():<26} {split.n_weeks:>5} "
            f"{len(rows):>8,} {positives:>6,} {rate:>6.2%}"
        )
    return "\n".join(lines)


def to_dict(frame: pd.DataFrame, plan: SplitPlan) -> dict:
    """Machine-readable split description for metadata and the report."""
    out: dict = {"purge_gap_days": plan.purge_days, "splits": {}}
    for split in (plan.train, plan.gap1, plan.valid, plan.gap2, plan.test):
        rows = frame[frame["snapshot_at"].isin(split.weeks)]
        positives = int(rows["churn_next_60d"].sum())
        key = split.name if split.name != "purge gap" else f"gap_before_{_next(plan, split)}"
        out["splits"][key] = {
            "start": str(split.start),
            "end": str(split.end),
            "weeks": split.n_weeks,
            "rows": int(len(rows)),
            "positives": positives,
            "positive_rate": positives / len(rows) if len(rows) else None,
        }
    return out


def _next(plan: SplitPlan, split: Split) -> str:
    return "validation" if split is plan.gap1 else "test"
