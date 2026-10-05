"""Baseline B: recency alone.

This is the baseline that decides whether the project has a question. If
knowing only how many days since the last payment attempt predicts churn about
as well as the full model, then trajectory and reliability features add
nothing and the research claim collapses. It must be beaten, and it must be
beaten by a visible margin.

The score is monotone in `recency_days` rather than a bare rule, so the model
produces a real precision-recall curve to plot against the others, while
`threshold_days` still gives the honest single-cut operating point.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features.definitions import OBSERVATION_WINDOW_DAYS


class RecencyBaseline:
    threshold_days: float

    def fit(self, valid: pd.DataFrame) -> "RecencyBaseline":
        """Pick the recency cut that maximises F1 on validation data."""
        from ml.evaluate import choose_threshold

        scores = self.predict_proba_1(valid)
        best = choose_threshold(valid["churn_next_60d"].to_numpy(), scores)
        self.threshold_days = best * OBSERVATION_WINDOW_DAYS
        return self

    def predict_proba_1(self, frame: pd.DataFrame) -> np.ndarray:
        """Days since last attempt, scaled into [0, 1]."""
        recency = frame["recency_days"].to_numpy(dtype=np.float64)
        return np.clip(recency / OBSERVATION_WINDOW_DAYS, 0.0, 1.0)
