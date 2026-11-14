"""Evaluation metrics for imbalanced binary risk scores.

Ranking metrics (PR-AUC, ROC-AUC, top-k) use `y_score`; probability metrics (Brier, log
loss) use `y_prob` when given. Isotonic calibration produces many ties, so a model's
ranking should be judged on its raw scores and its probabilities on calibrated values.
Ties at the top-k cutoff are broken randomly with a fixed seed, never by row order.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def evaluate(y_true, y_score, top_share: float = 0.05, y_prob=None,
             seed: int = 0) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    score = np.asarray(y_score, dtype=float)
    prob = np.clip(np.asarray(score if y_prob is None else y_prob, dtype=float), 1e-6, 1 - 1e-6)
    k = max(1, int(round(len(y) * top_share)))
    tiebreak = np.random.default_rng(seed).random(len(y))
    top = np.lexsort((tiebreak, -score))[:k]
    positives = y.sum()
    return {
        "pr_auc": float(average_precision_score(y, score)),
        "roc_auc": float(roc_auc_score(y, score)),
        "brier": float(brier_score_loss(y, prob)),
        "log_loss": float(log_loss(y, prob, labels=[0, 1])),
        "precision_at_top": float(y[top].mean()),
        "recall_at_top": float(y[top].sum() / positives) if positives else 0.0,
        "positive_rate": float(y.mean()),
    }
