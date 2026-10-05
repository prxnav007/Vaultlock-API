"""Load a trained model and score one merchant at a time.

Imports numpy and xgboost but deliberately not pandas, scikit-learn or shap:
this module runs inside the request path, and the serving environment has no
reason to carry the offline training stack.

Per-request explanations come from the booster's own `pred_contribs`, which is
exact TreeSHAP, rather than from the `shap` package. A unit test pins the two
together so the offline figures and the API response describe the same model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from ml.features.definitions import FEATURE_NAMES_FULL


class ModelContractError(RuntimeError):
    """The saved artifacts do not agree with the code loading them."""


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    model_version: str
    feature_names: tuple[str, ...]
    classification_threshold: float
    risk_band_edges: tuple[float, float]
    observation_window_days: int
    prediction_horizon_days: int
    min_tenure_days: int

    @classmethod
    def load(cls, path: Path) -> ModelMetadata:
        """Read metadata, inventing no defaults.

        Every field is required. A missing threshold silently becoming 0.5
        would mean serving a different decision rule than the one that was
        frozen on validation, which is exactly the drift this file exists to
        prevent.
        """
        if not path.exists():
            raise ModelContractError(f"model metadata not found: {path}")
        raw = json.loads(path.read_text())
        try:
            bands = raw["risk_band_edges"]
            return cls(
                model_version=raw["model_version"],
                feature_names=tuple(raw["feature_names"]),
                classification_threshold=float(raw["classification_threshold"]),
                risk_band_edges=(float(bands["medium"]), float(bands["high"])),
                observation_window_days=int(raw["observation_window_days"]),
                prediction_horizon_days=int(raw["prediction_horizon_days"]),
                min_tenure_days=int(raw["min_tenure_days"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelContractError(f"malformed model metadata: {exc}") from exc


class ChurnModel:
    """A booster plus the contract describing how it must be fed."""

    def __init__(self, booster: xgb.Booster, metadata: ModelMetadata) -> None:
        self.booster = booster
        self.metadata = metadata

    @classmethod
    def load(cls, model_path: Path, metadata_path: Path) -> ChurnModel:
        if not model_path.exists():
            raise ModelContractError(f"model artifact not found: {model_path}")
        metadata = ModelMetadata.load(metadata_path)

        booster = xgb.Booster()
        booster.load_model(str(model_path))

        unknown = set(metadata.feature_names) - set(FEATURE_NAMES_FULL)
        if unknown:
            raise ModelContractError(
                f"metadata names features this code cannot compute: {sorted(unknown)}"
            )
        # The booster records the feature order it was trained on. Comparing it
        # here turns a silently-wrong score into a refusal to start.
        trained_on = tuple(booster.feature_names or ())
        if trained_on and trained_on != metadata.feature_names:
            raise ModelContractError(
                "feature order disagrees between booster and metadata: "
                f"{trained_on} vs {metadata.feature_names}"
            )
        return cls(booster, metadata)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.metadata.feature_names

    def _matrix(self, features: np.ndarray) -> xgb.DMatrix:
        return xgb.DMatrix(
            features.reshape(1, -1),
            feature_names=list(self.feature_names),
            missing=np.nan,
        )

    def score(self, features: np.ndarray) -> float:
        """Churn score in [0, 1].

        Called a score rather than a probability: it has not been calibrated,
        so claiming it is the real-world likelihood of departure would overstate
        what was measured.
        """
        return float(self.booster.predict(self._matrix(features))[0])

    def contributions(self, features: np.ndarray) -> tuple[np.ndarray, float]:
        """Exact per-feature SHAP contributions, plus the base value.

        Returns log-odds contributions in `feature_names` order. The final
        column of `pred_contribs` is the bias term.
        """
        raw = self.booster.predict(self._matrix(features), pred_contribs=True)[0]
        return np.asarray(raw[:-1], dtype=np.float64), float(raw[-1])

    def risk_band(self, score: float) -> str:
        medium, high = self.metadata.risk_band_edges
        if score >= high:
            return "HIGH"
        if score >= medium:
            return "MEDIUM"
        return "LOW"

    def predicted_churn(self, score: float) -> bool:
        return score >= self.metadata.classification_threshold
