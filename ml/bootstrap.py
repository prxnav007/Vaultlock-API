"""Merchant-grouped bootstrap confidence intervals for the test-split metrics.

Resampling *rows* would badly understate the uncertainty here. One merchant
contributes up to nine test snapshots whose features and label are strongly
correlated -- consecutive weekly views of the same behaviour -- so row
resampling would treat nine near-copies as nine independent observations. The
resampling unit is therefore the merchant: draw merchants with replacement,
take all of their rows, and recompute.

The differences D-B and D-C are resampled on the *same* merchant draw as the
models themselves, so each interval is for the paired difference rather than
the gap between two independently-computed intervals.

Usage:
    python -m ml.bootstrap                 # 2000 resamples, writes into metrics.json
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml import config

MODELS = ("B", "C", "D")
DIFFERENCES = (("D", "B"), ("D", "C"))
DEFAULT_RESAMPLES = 2_000
ALPHA = 0.05


def interval(samples: np.ndarray, point: float) -> dict:
    """Percentile interval, reported alongside the point estimate."""
    finite = samples[np.isfinite(samples)]
    low, high = np.quantile(finite, [ALPHA / 2, 1 - ALPHA / 2])
    return {
        "point": float(point),
        "ci_low": float(low),
        "ci_high": float(high),
        "resamples_used": int(finite.size),
        "text": f"{point:.3f} [{low:.3f}, {high:.3f}]",
    }


def bootstrap(
    predictions: pd.DataFrame, n_resamples: int, seed: int
) -> dict:
    """Grouped bootstrap over merchants."""
    merchants = predictions["merchant_id"].to_numpy()
    unique = np.unique(merchants)
    # Row indices per merchant, so a resample is a concatenation of blocks.
    order = np.argsort(merchants, kind="stable")
    sorted_ids = merchants[order]
    starts = np.searchsorted(sorted_ids, unique, side="left")
    stops = np.searchsorted(sorted_ids, unique, side="right")
    blocks = [order[a:b] for a, b in zip(starts, stops, strict=True)]

    y = predictions["y_true"].to_numpy()
    scores = {name: predictions[f"score_{name.lower()}"].to_numpy() for name in MODELS}

    point = {
        name: float(average_precision_score(y, scores[name])) for name in MODELS
    }
    point_diff = {
        f"{a}-{b}": point[a] - point[b] for a, b in DIFFERENCES
    }

    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {name: [] for name in MODELS}
    diff_draws: dict[str, list[float]] = {f"{a}-{b}": [] for a, b in DIFFERENCES}

    for _ in range(n_resamples):
        picked = rng.integers(0, len(blocks), size=len(blocks))
        index = np.concatenate([blocks[i] for i in picked])
        y_resampled = y[index]
        # A resample with one class present has no defined average precision.
        if y_resampled.min() == y_resampled.max():
            continue
        values = {
            name: float(average_precision_score(y_resampled, scores[name][index]))
            for name in MODELS
        }
        for name in MODELS:
            draws[name].append(values[name])
        for a, b in DIFFERENCES:
            diff_draws[f"{a}-{b}"].append(values[a] - values[b])

    return {
        "method": "merchant-grouped percentile bootstrap",
        "resamples_requested": n_resamples,
        "confidence": 1 - ALPHA,
        "n_merchants": int(len(unique)),
        "n_rows": int(len(predictions)),
        "pr_auc": {
            name: interval(np.array(draws[name]), point[name]) for name in MODELS
        },
        "differences": {
            key: interval(np.array(diff_draws[key]), point_diff[key])
            for key in diff_draws
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    args = parser.parse_args(argv)
    if args.resamples < 1_000:
        parser.error("use at least 1000 resamples for a stable percentile interval")

    if not config.PREDICTIONS_TEST_PARQUET.exists():
        raise SystemExit("no test predictions; run python -m ml.train first")
    predictions = pd.read_parquet(config.PREDICTIONS_TEST_PARQUET)

    result = bootstrap(predictions, args.resamples, args.seed)

    metrics = json.loads(config.METRICS_PATH.read_text())
    metrics["bootstrap"] = result
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")

    used = result["pr_auc"]["D"]["resamples_used"]
    print(
        f"merchant-grouped bootstrap, {used:,} usable resamples of "
        f"{args.resamples:,} over {result['n_merchants']:,} merchants "
        f"({result['n_rows']:,} rows)\n"
    )
    print(f"{'quantity':<22} {'estimate':>8}  95% CI")
    print("-" * 48)
    for name in MODELS:
        entry = result["pr_auc"][name]
        print(
            f"{'PR-AUC ' + name:<22} {entry['point']:>8.3f}  "
            f"[{entry['ci_low']:.3f}, {entry['ci_high']:.3f}]"
        )
    for key, entry in result["differences"].items():
        print(
            f"{'PR-AUC ' + key:<22} {entry['point']:>+8.3f}  "
            f"[{entry['ci_low']:+.3f}, {entry['ci_high']:+.3f}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
