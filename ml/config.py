"""Paths and pipeline-wide knobs.

Window semantics are not redefined here -- they are re-exported from
`ml.features.definitions`, which is their single home.
"""
from __future__ import annotations

import os
from pathlib import Path

from ml.features.definitions import (  # noqa: F401  (re-exported on purpose)
    MIN_TENURE_DAYS,
    OBSERVATION_WINDOW_DAYS,
    PREDICTION_HORIZON_DAYS,
    RECENT_ACTIVITY_DAYS,
    SNAPSHOT_CADENCE_DAYS,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VAULT_DATA_DIR", ROOT / "data"))
GENERATED_DIR = DATA_DIR / "generated"
PROCESSED_DIR = DATA_DIR / "processed"
ARTIFACTS_DIR = Path(os.getenv("VAULT_ARTIFACTS_DIR", ROOT / "artifacts"))

SNAPSHOTS_PARQUET = PROCESSED_DIR / "merchant_snapshots.parquet"
PROFILES_PARQUET = GENERATED_DIR / "merchant_profiles.parquet"

GENERATION_SUMMARY = ARTIFACTS_DIR / "generation_summary.json"
DATASET_SUMMARY = ARTIFACTS_DIR / "dataset_summary.json"
MODEL_PATH = ARTIFACTS_DIR / "xgboost_model.json"
MODEL_RFM_PATH = ARTIFACTS_DIR / "xgboost_model_rfm.json"
MODEL_METADATA_PATH = ARTIFACTS_DIR / "model_metadata.json"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
SEARCH_RESULTS_PATH = ARTIFACTS_DIR / "search_results.json"
PREDICTIONS_TEST_PARQUET = ARTIFACTS_DIR / "predictions_test.parquet"
PREDICTIONS_VALID_PARQUET = ARTIFACTS_DIR / "predictions_valid.parquet"
SHAP_TEST_NPZ = ARTIFACTS_DIR / "shap_test.npz"
SHAP_GLOBAL_PATH = ARTIFACTS_DIR / "shap_global.json"
EXEMPLARS_PATH = ARTIFACTS_DIR / "exemplars.json"
REPORT_FACTS_PATH = ARTIFACTS_DIR / "report_facts.json"

RANDOM_SEED = 42

# Chronological split shape, allocated backwards from the last snapshot week.
# The purge gap must cover the label horizon or a training row's future window
# overlaps a validation/test decision point.
PURGE_WEEKS = 9
VALID_WEEKS = 10
TEST_WEEKS = 9
assert PURGE_WEEKS * 7 >= PREDICTION_HORIZON_DAYS

MODEL_VERSION = "xgb-v1"


def ensure_dirs() -> None:
    for directory in (GENERATED_DIR, PROCESSED_DIR, ARTIFACTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
