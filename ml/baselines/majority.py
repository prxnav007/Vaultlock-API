"""Baseline A: the majority classifier.

It never predicts churn. Its purpose is to establish the floor: on a dataset
with a 2% positive rate, a model that always says "no" is 98% accurate, which
is why accuracy is not reported anywhere in this project. Its PR-AUC equals
the positive rate by definition, which doubles as a check on the metric code.
"""
from __future__ import annotations

import numpy as np


class MajorityBaseline:
    prior: float

    def fit(self, y_train: np.ndarray) -> "MajorityBaseline":
        self.prior = float(np.mean(y_train))
        return self

    def predict_proba_1(self, n_rows: int) -> np.ndarray:
        """One constant score per row, so ranking carries no information."""
        return np.full(n_rows, self.prior, dtype=np.float64)
