"""One scoring function, used for every model.

All four models are measured by identical code so the comparison in the report
cannot be an artefact of how each was evaluated.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)


def metrics_at(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    """Threshold-free ranking quality plus the operating point's behaviour.

    PR-AUC leads because the positive class is rare: ROC-AUC flatters a model
    on imbalanced data by rewarding it for the many easy negatives.
    """
    predicted = (scores >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predicted, average="binary", zero_division=0
    )
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    constant = float(np.ptp(scores)) == 0.0
    return {
        "pr_auc": float(average_precision_score(y_true, scores)),
        # Undefined for a model that emits one constant score; reporting 0.5
        # would imply a measurement that was not made.
        "roc_auc": None if constant else float(roc_auc_score(y_true, scores)),
        "f1": float(f1),
        # Precision is undefined when nothing is flagged, which is exactly what
        # the majority baseline does.
        "precision": float(precision) if (tp + fp) else None,
        "recall": float(recall),
        "threshold": float(threshold),
        "confusion_matrix": {
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn),
            "tn": int(tn),
        },
        "n_rows": int(len(y_true)),
        "n_positives": int(y_true.sum()),
    }


def choose_threshold(
    y_true: np.ndarray, scores: np.ndarray, grid: np.ndarray | None = None
) -> float:
    """The F1-maximising threshold on the data given.

    Only ever called with validation data. 0.5 is not assumed to be the
    operating point, and the test split never informs this choice.
    """
    candidates = np.arange(0.01, 1.00, 0.01) if grid is None else grid
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in candidates:
        _, _, f1, _ = precision_recall_fscore_support(
            y_true, (scores >= threshold).astype(int), average="binary", zero_division=0
        )
        if f1 > best_f1:
            best_threshold, best_f1 = float(threshold), float(f1)
    return best_threshold
