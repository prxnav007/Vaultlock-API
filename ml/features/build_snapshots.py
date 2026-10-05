"""Build the leakage-safe merchant x snapshot training table.

One row is one merchant observed at one weekly snapshot time t: twelve features
summarising the 90 days up to t, and a label describing the 60 days after it.
Both come from `ml.features.definitions` -- the same functions the API calls --
so there is no second implementation to drift.

Usage:
    python -m ml.features.build_snapshots
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ml import config, io
from ml.features.definitions import (
    FEATURE_NAMES_FULL,
    INT_FEATURES,
    MIN_TENURE_DAYS,
    MerchantHistory,
    PREDICTION_HORIZON_DAYS,
    SECONDS_PER_DAY,
    SNAPSHOT_CADENCE_DAYS,
    TERMINAL_STATUSES,
    churn_next_60d,
    compute_features,
    eligibility,
)

METADATA_COLUMNS = ("merchant_id", "snapshot_at")
LABEL_COLUMN = "churn_next_60d"


def snapshot_grid(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Weekly snapshot times, anchored to the first Sunday midnight UTC.

    Weekly rather than daily because consecutive days produce near-duplicate
    rows; weekly still gives many observations of each merchant's lifecycle.
    """
    first = start.tz_convert("UTC").normalize()
    first += pd.Timedelta(days=(6 - first.dayofweek) % 7)
    return pd.date_range(
        first, end.tz_convert("UTC"), freq=f"{SNAPSHOT_CADENCE_DAYS}D", tz="UTC"
    )


def iter_histories(
    merchants: pd.DataFrame, payments: pd.DataFrame
) -> Iterator[MerchantHistory]:
    """Yield one history per merchant, as views into the full ledger.

    `payments` must arrive sorted by (merchant_id, created_at) -- see
    `ml.io.read_payments`. Each merchant's block is then a contiguous slice,
    so no row is copied and no mask is built.
    """
    created = (
        payments["created_at"].to_numpy(dtype="datetime64[ns]").astype(np.float64)
        / 1e9
    )
    amounts = payments["amount_minor"].to_numpy(dtype=np.int64)
    status = payments["status"].to_numpy(dtype=object)
    is_success = status == "SUCCESS"
    is_terminal = np.isin(status, list(TERMINAL_STATUSES))

    keys = payments["merchant_id"].astype(str).to_numpy()
    # Block boundaries, found once for the whole ledger.
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]]) if keys.size else []
    bounds = {keys[s]: (s, e) for s, e in zip(starts, [*starts[1:], keys.size])} if len(starts) else {}

    joined = merchants.set_index(merchants["merchant_id"].astype(str))["joined_at"]
    for merchant_id, joined_at in joined.items():
        lo, hi = bounds.get(merchant_id, (0, 0))
        yield MerchantHistory.from_arrays(
            merchant_id=merchant_id,
            joined_at=pd.Timestamp(joined_at).tz_convert("UTC").timestamp(),
            created_at=created[lo:hi],
            amount_minor=amounts[lo:hi],
            is_success=is_success[lo:hi],
            is_terminal=is_terminal[lo:hi],
        )


def build(
    merchants: pd.DataFrame,
    payments: pd.DataFrame,
    grid: pd.DatetimeIndex,
    dataset_end: pd.Timestamp,
) -> tuple[pd.DataFrame, Counter]:
    """Every eligible merchant x snapshot row, plus why rows were rejected."""
    grid_epoch = grid.to_numpy(dtype="datetime64[ns]").astype(np.float64) / 1e9
    end_epoch = dataset_end.timestamp()
    # A snapshot is only usable once the merchant has 90 days of tenure and
    # while 60 observable days still remain, so each merchant sees a sub-range
    # of the grid rather than all of it.
    last_usable = end_epoch - PREDICTION_HORIZON_DAYS * SECONDS_PER_DAY

    rejected: Counter = Counter()
    records: list[dict] = []
    for history in iter_histories(merchants, payments):
        earliest = history.joined_at + MIN_TENURE_DAYS * SECONDS_PER_DAY
        lo = int(np.searchsorted(grid_epoch, earliest, side="left"))
        hi = int(np.searchsorted(grid_epoch, last_usable, side="right"))
        for index in range(lo, hi):
            t = float(grid_epoch[index])
            verdict = eligibility(history, t, end_epoch, mode="training")
            if not verdict.ok:
                rejected[verdict.reason] += 1
                continue
            row = {
                "merchant_id": history.merchant_id,
                "snapshot_at": grid[index],
                **compute_features(history, t),
                LABEL_COLUMN: churn_next_60d(history, t),
            }
            records.append(row)

    frame = pd.DataFrame.from_records(records)
    return frame, rejected


ARROW_SCHEMA = pa.schema(
    [
        ("merchant_id", pa.string()),
        ("snapshot_at", pa.timestamp("us", tz="UTC")),
        *[
            (name, pa.int32() if name in INT_FEATURES else pa.float64())
            for name in FEATURE_NAMES_FULL
        ],
        (LABEL_COLUMN, pa.int8()),
    ]
)


def write_parquet(frame: pd.DataFrame, path) -> None:
    """Write with an explicit schema.

    Counts are int32 because they are never missing; anything that can be
    absent stays float64 so a genuine NaN survives the round trip instead of
    being coerced to zero.
    """
    typed = frame.copy()
    for name in FEATURE_NAMES_FULL:
        typed[name] = typed[name].astype("int32" if name in INT_FEATURES else "float64")
    typed[LABEL_COLUMN] = typed[LABEL_COLUMN].astype("int8")
    table = pa.Table.from_pandas(typed, schema=ARROW_SCHEMA, preserve_index=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")


def summarize(
    frame: pd.DataFrame, grid: pd.DatetimeIndex, rejected: Counter
) -> dict:
    positives = int(frame[LABEL_COLUMN].sum())
    weekly = (
        frame.groupby("snapshot_at")[LABEL_COLUMN]
        .agg(rows="size", positives="sum")
        .reset_index()
    )
    return {
        "eligible_rows": int(len(frame)),
        "positives": positives,
        "positive_rate": positives / len(frame) if len(frame) else 0.0,
        "merchants_represented": int(frame["merchant_id"].nunique()),
        "snapshot_weeks": int(frame["snapshot_at"].nunique()),
        "first_snapshot": str(frame["snapshot_at"].min()),
        "last_snapshot": str(frame["snapshot_at"].max()),
        "grid_first": str(grid[0]),
        "grid_last": str(grid[-1]),
        "rejected": dict(rejected),
        "missing_by_feature": {
            name: int(frame[name].isna().sum()) for name in FEATURE_NAMES_FULL
        },
        "per_week": [
            {
                "snapshot_at": str(row.snapshot_at),
                "rows": int(row.rows),
                "positives": int(row.positives),
            }
            for row in weekly.itertuples()
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(config.SNAPSHOTS_PARQUET))
    args = parser.parse_args(argv)

    merchants = io.read_merchants()
    payments = io.read_payments()
    dataset_end = io.latest_payment_time()
    print(
        f"{len(merchants):,} merchants, {len(payments):,} payments, "
        f"history ends {dataset_end}",
        file=sys.stderr,
    )

    grid = snapshot_grid(
        pd.Timestamp(payments["created_at"].min()).tz_convert("UTC"), dataset_end
    )
    frame, rejected = build(merchants, payments, grid, dataset_end)
    if frame.empty:
        raise SystemExit("no eligible snapshots -- check the generated history")

    frame = frame.sort_values(["snapshot_at", "merchant_id"]).reset_index(drop=True)
    write_parquet(frame, config.SNAPSHOTS_PARQUET)

    summary = summarize(frame, grid, rejected)
    config.ensure_dirs()
    config.DATASET_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    terse = {k: v for k, v in summary.items() if k != "per_week"}
    print(json.dumps(terse, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
