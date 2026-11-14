"""Evaluation metrics for imbalanced binary risk scores."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def evaluate(y_true, y_score, top_share: float = 0.05) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    s = np.clip(np.asarray(y_score, dtype=float), 1e-6, 1 - 1e-6)
    k = max(1, int(round(len(y) * top_share)))
    top = np.argsort(-s, kind="stable")[:k]
    positives = y.sum()
    return {
        "pr_auc": float(average_precision_score(y, s)),
        "roc_auc": float(roc_auc_score(y, s)),
        "brier": float(brier_score_loss(y, s)),
        "log_loss": float(log_loss(y, s, labels=[0, 1])),
        "precision_at_top": float(y[top].mean()),
        "recall_at_top": float(y[top].sum() / positives) if positives else 0.0,
        "positive_rate": float(y.mean()),
    }
