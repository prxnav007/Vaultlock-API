"""Explain the final model with SHAP, and pin the report's exemplar merchants.

SHAP shows how each feature moved the model's output. It does not show that the
feature caused the merchant to leave, and nothing here should be read as a
causal claim.

The `shap` package is used only in this offline step. The API computes the same
quantities through the booster's `pred_contribs`, and a test pins the two
together, so the serving environment never needs this dependency.

Usage:
    python -m ml.explain
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from ml import config
from ml.features.definitions import FEATURE_NAMES_FULL

LABEL = "churn_next_60d"
BEESWARM_SAMPLE = 420


def load_test_rows() -> pd.DataFrame:
    """The test split, with features joined onto the saved predictions."""
    predictions = pd.read_parquet(config.PREDICTIONS_TEST_PARQUET)
    snapshots = pd.read_parquet(config.SNAPSHOTS_PARQUET)
    merged = predictions.merge(
        snapshots, on=["merchant_id", "snapshot_at"], how="left", validate="one_to_one"
    )
    if merged[list(FEATURE_NAMES_FULL)].isna().all(axis=1).any():
        raise SystemExit("prediction rows did not join onto the snapshot table")
    return merged


def global_ranking(values: np.ndarray, names: tuple[str, ...]) -> list[dict]:
    """Features ordered by mean absolute SHAP value over the test split."""
    mean_abs = np.abs(values).mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    return [
        {"feature": names[i], "mean_abs_shap": float(mean_abs[i])} for i in order
    ]


def pick_exemplars(
    rows: pd.DataFrame, values: np.ndarray, base_value: float, threshold: float
) -> dict:
    """Choose one high-risk and one low-risk merchant, deterministically.

    Both come from the final week of the test split, so the snapshot the figures
    describe is as close as possible to the instant the endpoint is screenshotted
    at. Ties break on merchant_id so reruns pick the same merchants.
    """
    last_week = rows["snapshot_at"].max()
    pool = rows[rows["snapshot_at"] == last_week]

    high_pool = pool[(pool["y_true"] == 1) & (pool["score_d"] >= threshold)]
    if high_pool.empty:  # no true positive that week; fall back to the whole split
        high_pool = rows[(rows["y_true"] == 1) & (rows["score_d"] >= threshold)]
    high = high_pool.sort_values(["score_d", "merchant_id"], ascending=[False, True]).iloc[0]

    # "Steady recent activity" has to be true of the low-risk example, or the
    # comparison in the report is between a quiet merchant and a dormant one.
    low_pool = pool[(pool["y_true"] == 0) & (pool["tx_count_30d"] >= 4)]
    if low_pool.empty:
        low_pool = pool[pool["y_true"] == 0]
    low = low_pool.sort_values(["score_d", "merchant_id"], ascending=[True, True]).iloc[0]

    out = {}
    for name, row in (("high_risk", high), ("low_risk", low)):
        index = rows.index.get_loc(row.name)
        out[name] = {
            "merchant_id": str(row["merchant_id"]),
            "snapshot_at": str(row["snapshot_at"]),
            "y_true": int(row["y_true"]),
            "score_d": float(row["score_d"]),
            "base_value": base_value,
            "features": {
                feature: {
                    "value": None
                    if pd.isna(row[feature])
                    else float(row[feature]),
                    "shap": float(values[index, i]),
                }
                for i, feature in enumerate(FEATURE_NAMES_FULL)
            },
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    metadata = json.loads(config.MODEL_METADATA_PATH.read_text())
    threshold = float(metadata["classification_threshold"])
    features = tuple(metadata["feature_names"])

    booster = xgb.Booster()
    booster.load_model(str(config.MODEL_PATH))

    rows = load_test_rows().reset_index(drop=True)
    matrix = rows[list(features)]
    print(f"explaining {len(rows):,} test rows", file=sys.stderr)

    explainer = shap.TreeExplainer(booster)
    values = np.asarray(explainer.shap_values(matrix), dtype=np.float64)
    base_value = float(np.ravel(explainer.expected_value)[0])

    ranking = global_ranking(values, features)
    exemplars = pick_exemplars(rows, values, base_value, threshold)

    rng = np.random.default_rng(config.RANDOM_SEED)
    sample = rng.choice(
        len(rows), size=min(BEESWARM_SAMPLE, len(rows)), replace=False
    )

    config.ensure_dirs()
    np.savez_compressed(
        config.SHAP_TEST_NPZ,
        values=values.astype(np.float32),
        data=matrix.to_numpy(dtype=np.float32),
        base_value=base_value,
        feature_names=np.array(features),
        merchant_id=rows["merchant_id"].to_numpy().astype(str),
        snapshot_at=rows["snapshot_at"].astype(str).to_numpy(),
        subsample_index=np.sort(sample),
    )
    config.SHAP_GLOBAL_PATH.write_text(
        json.dumps({"base_value": base_value, "ranking": ranking}, indent=2) + "\n"
    )
    config.EXEMPLARS_PATH.write_text(json.dumps(exemplars, indent=2) + "\n")

    print("\nglobal feature importance (mean |SHAP|):")
    for entry in ranking:
        print(f"  {entry['feature']:<30} {entry['mean_abs_shap']:.4f}")
    print("\nexemplars:")
    for name, row in exemplars.items():
        print(
            f"  {name:<10} {row['merchant_id']}  score={row['score_d']:.3f}  "
            f"y_true={row['y_true']}  at {row['snapshot_at']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
