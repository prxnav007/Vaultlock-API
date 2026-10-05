"""Train and compare the four required models.

A: majority         the imbalance floor
B: recency only     the baseline that must be beaten
C: RFM + tenure     recency, frequency, monetary, tenure
D: C + reliability  adds the three failure-rate features

The question the comparison answers is whether transaction trajectory and
payment reliability improve future-churn prediction beyond a simple recency
signal. D minus C is the part of that question about reliability specifically.

Usage:
    python -m ml.train            # full search, writes artifacts
    python -m ml.train --quick    # one configuration, for the feasibility gate
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import xgboost as xgb

from ml import config, splits
from ml.baselines.majority import MajorityBaseline
from ml.baselines.recency import RecencyBaseline
from ml.evaluate import choose_threshold, metrics_at
from ml.features.definitions import (
    FEATURE_NAMES_FULL,
    FEATURE_NAMES_RFM,
    MIN_TENURE_DAYS,
    OBSERVATION_WINDOW_DAYS,
    PREDICTION_HORIZON_DAYS,
    SNAPSHOT_CADENCE_DAYS,
)

LABEL = "churn_next_60d"

FEATURE_SETS = {"C": FEATURE_NAMES_RFM, "D": FEATURE_NAMES_FULL}

# A small, legible search over the eight parameters the spec names. Deliberately
# not a genetic algorithm: feature correctness and generator realism matter far
# more here than the last hundredth of PR-AUC.
HYPERPARAM_GRID: tuple[dict, ...] = tuple(
    {
        "max_depth": depth,
        "learning_rate": lr,
        "n_estimators": trees,
        "min_child_weight": min_child,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.0,
        "reg_lambda": 1.0,
    }
    for depth in (3, 4, 6)
    for lr in (0.05, 0.10)
    for trees in (300, 600)
    for min_child in (1, 5)
)
QUICK_PARAMS = {
    "max_depth": 4,
    "learning_rate": 0.1,
    "n_estimators": 300,
    "min_child_weight": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
}


# <listing:5.3>
def scale_pos_weight(y_train: np.ndarray) -> float:
    """Negatives over positives, computed on the TRAINING split only.

    Deriving it from the whole dataset would leak the test period's class
    balance into training. This is the first and only imbalance remedy here:
    resampling schemes come later, if ever, once the baseline is trusted.
    """
    positives = int(y_train.sum())
    if positives == 0:
        raise ValueError("training split contains no positive labels")
    return float(len(y_train) - positives) / positives


def fit_model(
    train: pd.DataFrame, features: tuple[str, ...], params: dict
) -> xgb.XGBClassifier:
    """Fit one classifier. NaN is passed through as a genuine missing value."""
    model = xgb.XGBClassifier(
        **params,
        objective="binary:logistic",
        eval_metric="aucpr",
        tree_method="hist",
        missing=np.nan,
        scale_pos_weight=scale_pos_weight(train[LABEL].to_numpy()),
        random_state=config.RANDOM_SEED,
        n_jobs=0,
    )
    model.fit(train[list(features)], train[LABEL])
    return model
# </listing:5.3>


def predict(model: xgb.XGBClassifier, frame: pd.DataFrame, features) -> np.ndarray:
    return model.predict_proba(frame[list(features)])[:, 1]


def search(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    features: tuple[str, ...],
    grid: tuple[dict, ...],
) -> tuple[dict, list[dict]]:
    """Pick hyperparameters on validation PR-AUC. The test split is untouched."""
    from sklearn.metrics import average_precision_score

    y_valid = valid[LABEL].to_numpy()
    trials: list[dict] = []
    best, best_score = grid[0], -1.0
    for i, params in enumerate(grid, start=1):
        model = fit_model(train, features, params)
        score = float(average_precision_score(y_valid, predict(model, valid, features)))
        trials.append({"params": params, "valid_pr_auc": score})
        if score > best_score:
            best, best_score = params, score
        print(f"  [{i}/{len(grid)}] valid PR-AUC {score:.4f}", file=sys.stderr)
    return best, trials


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:  # pragma: no cover - git may be absent
        return None


def risk_band_edges(threshold: float, valid_scores: np.ndarray) -> tuple[float, float]:
    """Where LOW becomes MEDIUM, and MEDIUM becomes HIGH.

    Anchored on the frozen threshold: MEDIUM begins there, so HIGH is a strict
    subset of "predicted to churn". HIGH would sit at twice the threshold, but
    if that is unreachable the upper edge falls back to a high quantile of the
    validation scores, so the band is always attainable by some merchant.
    """
    low_edge = threshold
    high_edge = threshold * 2.0
    if high_edge >= 1.0 or high_edge >= float(np.max(valid_scores)):
        high_edge = float(np.quantile(valid_scores, 0.99))
        if high_edge <= low_edge:
            high_edge = float((low_edge + 1.0) / 2.0)
    return low_edge, high_edge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="skip the search and use one configuration (feasibility gate)",
    )
    args = parser.parse_args(argv)

    frame = pd.read_parquet(config.SNAPSHOTS_PARQUET)
    weeks = sorted(frame["snapshot_at"].unique())
    plan = splits.plan_splits([pd.Timestamp(w) for w in weeks])
    print(splits.describe(frame, plan), file=sys.stderr)

    parts = splits.apply(frame, plan)
    train, valid, test = parts["train"], parts["validation"], parts["test"]
    y_valid, y_test = valid[LABEL].to_numpy(), test[LABEL].to_numpy()

    grid = (QUICK_PARAMS,) if args.quick else HYPERPARAM_GRID
    scores_valid: dict[str, np.ndarray] = {}
    scores_test: dict[str, np.ndarray] = {}
    chosen: dict[str, dict] = {}
    models: dict[str, xgb.XGBClassifier] = {}

    # A: majority
    majority = MajorityBaseline().fit(train[LABEL].to_numpy())
    scores_valid["A"] = majority.predict_proba_1(len(valid))
    scores_test["A"] = majority.predict_proba_1(len(test))

    # B: recency only
    recency = RecencyBaseline().fit(valid)
    scores_valid["B"] = recency.predict_proba_1(valid)
    scores_test["B"] = recency.predict_proba_1(test)

    # C and D: XGBoost over the two feature sets
    for name, features in FEATURE_SETS.items():
        print(f"searching model {name} ({len(features)} features)", file=sys.stderr)
        params, trials = search(train, valid, features, grid)
        model = fit_model(train, features, params)
        models[name] = model
        chosen[name] = {"params": params, "trials": trials}
        scores_valid[name] = predict(model, valid, features)
        scores_test[name] = predict(model, test, features)

    # Thresholds are chosen on validation for every model, so each operating
    # point in the report is a real decision rather than an arbitrary 0.5.
    thresholds = {
        name: choose_threshold(y_valid, scores_valid[name]) for name in scores_valid
    }
    # The majority model emits one constant score, so no cut separates anything;
    # fixing it above that constant makes explicit that it flags nothing.
    thresholds["A"] = float(majority.prior + 1e-9)

    results_valid = {
        name: metrics_at(y_valid, scores_valid[name], thresholds[name])
        for name in scores_valid
    }
    # The test split is scored exactly once, here, after every threshold is set.
    results_test = {
        name: metrics_at(y_test, scores_test[name], thresholds[name])
        for name in scores_test
    }

    low_edge, high_edge = risk_band_edges(thresholds["D"], scores_valid["D"])
    spw = scale_pos_weight(train[LABEL].to_numpy())

    config.ensure_dirs()
    models["D"].save_model(config.MODEL_PATH)
    models["C"].save_model(config.MODEL_RFM_PATH)

    metadata = {
        "model_version": config.MODEL_VERSION,
        "feature_names": list(FEATURE_NAMES_FULL),
        "observation_window_days": OBSERVATION_WINDOW_DAYS,
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "snapshot_cadence_days": SNAPSHOT_CADENCE_DAYS,
        "min_tenure_days": MIN_TENURE_DAYS,
        "classification_threshold": thresholds["D"],
        "risk_band_edges": {"medium": low_edge, "high": high_edge},
        "risk_band_rule": (
            "LOW below the frozen threshold; MEDIUM from the threshold to the "
            "high edge; HIGH at or above it. The high edge is twice the "
            "threshold, or the 99th percentile of validation scores when twice "
            "the threshold is unreachable."
        ),
        "training_data_time_range": [str(plan.train.start), str(plan.train.end)],
        "validation_data_time_range": [str(plan.valid.start), str(plan.valid.end)],
        "test_data_time_range": [str(plan.test.start), str(plan.test.end)],
        "purge_gap_days": plan.purge_days,
        "scale_pos_weight": spw,
        "selected_hyperparameters": chosen["D"]["params"],
        "trained_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "quick_mode": args.quick,
    }
    config.MODEL_METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n")

    metrics = {
        "label_balance": splits.to_dict(frame, plan),
        "test": results_test,
        "validation": results_valid,
        "thresholds": thresholds,
        "scale_pos_weight": spw,
        "selected_hyperparameters": {k: v["params"] for k, v in chosen.items()},
        "delta_pr_auc_failure_features": (
            results_test["D"]["pr_auc"] - results_test["C"]["pr_auc"]
        ),
        "delta_pr_auc_over_recency": (
            results_test["D"]["pr_auc"] - results_test["B"]["pr_auc"]
        ),
        "quick_mode": args.quick,
    }
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n")
    config.SEARCH_RESULTS_PATH.write_text(
        json.dumps({k: v["trials"] for k, v in chosen.items()}, indent=2) + "\n"
    )

    # Per-row test scores, so the report's precision-recall curves are measured
    # rather than fitted to a summary statistic.
    pd.DataFrame(
        {
            "merchant_id": test["merchant_id"].to_numpy(),
            "snapshot_at": test["snapshot_at"].to_numpy(),
            "y_true": y_test,
            **{f"score_{name.lower()}": scores_test[name] for name in scores_test},
        }
    ).to_parquet(config.PREDICTIONS_TEST_PARQUET, index=False)
    pd.DataFrame(
        {
            "y_true": y_valid,
            **{f"score_{name.lower()}": scores_valid[name] for name in scores_valid},
        }
    ).to_parquet(config.PREDICTIONS_VALID_PARQUET, index=False)

    print(report_table(results_test, thresholds))
    print(
        f"\nscale_pos_weight {spw:.2f}  |  frozen threshold (D) "
        f"{thresholds['D']:.2f}  |  bands: MEDIUM>={low_edge:.2f} HIGH>={high_edge:.2f}"
    )
    print(
        f"D - C = {metrics['delta_pr_auc_failure_features']:+.4f} PR-AUC   "
        f"D - B = {metrics['delta_pr_auc_over_recency']:+.4f} PR-AUC"
    )
    return 0


LABELS = {
    "A": "A - majority",
    "B": "B - recency only",
    "C": "C - RFM + tenure",
    "D": "D - RFM + failure",
}


def report_table(results: dict, thresholds: dict) -> str:
    header = (
        f"{'model':<20} {'PR-AUC':>7} {'F1':>6} {'prec':>6} {'recall':>7} {'ROC-AUC':>8}"
    )
    lines = [header, "-" * len(header)]
    for name in ("A", "B", "C", "D"):
        row = results[name]
        precision = "    -  " if row["precision"] is None else f"{row['precision']:>6.3f}"
        roc = "     -  " if row["roc_auc"] is None else f"{row['roc_auc']:>8.3f}"
        lines.append(
            f"{LABELS[name]:<20} {row['pr_auc']:>7.3f} {row['f1']:>6.3f} "
            f"{precision} {row['recall']:>7.3f} {roc}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
