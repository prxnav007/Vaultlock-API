"""The two ways of building a history must agree exactly.

There is only one implementation of each feature, so the features themselves
cannot drift. What *can* drift is how a history gets assembled: the API builds
one from a result set with `from_rows`, while the offline builder slices array
views with `from_arrays`. If those two disagree -- on sort order, on dtype, on
how a status string maps to a flag -- then training and serving diverge even
though they call identical arithmetic. This pins them together.
"""
import math
from datetime import UTC, datetime, timedelta

import numpy as np

from ml.features.definitions import (
    FEATURE_NAMES_FULL,
    MerchantHistory,
    SECONDS_PER_DAY,
    TERMINAL_STATUSES,
    compute_features,
)

T0 = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
JOINED = T0 - timedelta(days=500)


def random_rows(seed: int, n: int) -> list[tuple[datetime, int, str]]:
    """A history including windows that produce NaN features."""
    rng = np.random.default_rng(seed)
    offsets = np.sort(rng.uniform(-400.0, 20.0, size=n))
    # Heavily skewed towards FAILED so some windows have no SUCCESS at all,
    # and some have no terminal attempt either.
    statuses = rng.choice(["SUCCESS", "FAILED"], size=n, p=[0.35, 0.65])
    return [
        (
            T0 + timedelta(seconds=float(offset) * SECONDS_PER_DAY),
            int(rng.integers(100, 500_000)),
            str(status),
        )
        for offset, status in zip(offsets, statuses, strict=True)
    ]


def as_arrays(rows: list[tuple[datetime, int, str]]) -> MerchantHistory:
    """Build the way the offline snapshot builder does."""
    return MerchantHistory.from_arrays(
        merchant_id="m1",
        joined_at=JOINED.timestamp(),
        created_at=np.array([r[0].timestamp() for r in rows], dtype=np.float64),
        amount_minor=np.array([r[1] for r in rows], dtype=np.int64),
        is_success=np.array([r[2] == "SUCCESS" for r in rows], dtype=bool),
        is_terminal=np.array([r[2] in TERMINAL_STATUSES for r in rows], dtype=bool),
    )


def test_both_constructors_produce_identical_features() -> None:
    saw_nan = False
    for seed in range(40):
        rows = random_rows(seed, n=int(4 + seed % 30))
        from_rows = compute_features(MerchantHistory.from_rows("m1", JOINED, rows), T0.timestamp())
        from_arrays = compute_features(as_arrays(rows), T0.timestamp())

        assert from_rows.keys() == from_arrays.keys()
        for name in FEATURE_NAMES_FULL:
            a, b = from_rows[name], from_arrays[name]
            if math.isnan(a) or math.isnan(b):
                saw_nan = True
                assert math.isnan(a) and math.isnan(b), name
            else:
                assert a == b, f"{name}: {a} != {b} (seed {seed})"

    # The comparison is only meaningful if it exercised the missing-value paths.
    assert saw_nan, "no NaN-producing window was covered"


def test_unsorted_rows_are_ordered_by_from_rows() -> None:
    """The API cannot assume its result set arrives sorted."""
    rows = random_rows(7, n=20)
    shuffled = [rows[i] for i in np.random.default_rng(0).permutation(len(rows))]
    ordered = compute_features(MerchantHistory.from_rows("m1", JOINED, rows), T0.timestamp())
    jumbled = compute_features(
        MerchantHistory.from_rows("m1", JOINED, shuffled), T0.timestamp()
    )
    for name in FEATURE_NAMES_FULL:
        a, b = ordered[name], jumbled[name]
        assert (math.isnan(a) and math.isnan(b)) or a == b, name
