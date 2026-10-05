"""The API's explanations must equal the ones the report's figures are drawn from.

The request path uses the booster's `pred_contribs` so that the serving
environment needs neither scikit-learn nor shap. That is only safe if the two
agree exactly -- otherwise the top factors in an API response would describe a
slightly different model than the SHAP figures in the report.
"""
import json

import numpy as np
import pytest

from ml import config
from ml.inference import ChurnModel


@pytest.fixture(scope="module")
def model() -> ChurnModel:
    if not config.MODEL_PATH.exists() or not config.MODEL_METADATA_PATH.exists():
        pytest.skip("no trained model; run python -m ml.train")
    return ChurnModel.load(config.MODEL_PATH, config.MODEL_METADATA_PATH)


def test_pred_contribs_matches_the_shap_library(model: ChurnModel) -> None:
    shap = pytest.importorskip("shap")

    rng = np.random.default_rng(config.RANDOM_SEED)
    n_features = len(model.feature_names)
    rows = rng.normal(size=(6, n_features)).astype(np.float32)
    # Include a row with missing values: NaN handling is where two
    # implementations are most likely to diverge.
    rows[0, :3] = np.nan

    explainer = shap.TreeExplainer(model.booster)
    expected = np.asarray(explainer.shap_values(rows), dtype=np.float64)

    for i, row in enumerate(rows):
        contributions, base = model.contributions(row)
        np.testing.assert_allclose(contributions, expected[i], rtol=1e-5, atol=1e-6)
        np.testing.assert_allclose(
            base, np.ravel(explainer.expected_value)[0], rtol=1e-5
        )


def test_metadata_feature_order_matches_the_booster(model: ChurnModel) -> None:
    """A reordered feature list would silently score a nonsense vector."""
    trained_on = tuple(model.booster.feature_names or ())
    assert trained_on == model.feature_names


def test_risk_bands_are_reachable_and_ordered(model: ChurnModel) -> None:
    medium, high = model.metadata.risk_band_edges
    assert 0.0 < medium < high <= 1.0
    assert model.risk_band(0.0) == "LOW"
    assert model.risk_band(medium) == "MEDIUM"
    assert model.risk_band(high) == "HIGH"
    assert model.risk_band(1.0) == "HIGH"


def test_predicted_churn_uses_the_frozen_threshold(model: ChurnModel) -> None:
    threshold = model.metadata.classification_threshold
    assert not model.predicted_churn(threshold - 1e-6)
    assert model.predicted_churn(threshold)


def test_window_constants_in_metadata_match_the_code(model: ChurnModel) -> None:
    """A model served under different window semantics is a different model."""
    from ml.features.definitions import (
        MIN_TENURE_DAYS,
        OBSERVATION_WINDOW_DAYS,
        PREDICTION_HORIZON_DAYS,
        SNAPSHOT_CADENCE_DAYS,
    )

    raw = json.loads(config.MODEL_METADATA_PATH.read_text())
    assert raw["observation_window_days"] == OBSERVATION_WINDOW_DAYS
    assert raw["prediction_horizon_days"] == PREDICTION_HORIZON_DAYS
    assert raw["snapshot_cadence_days"] == SNAPSHOT_CADENCE_DAYS
    assert raw["min_tenure_days"] == MIN_TENURE_DAYS
