import numpy as np
import pytest

from procurement_risk.model.metrics import evaluate


def test_evaluate_perfect_and_random():
    y = np.array([0] * 90 + [1] * 10)
    perfect = evaluate(y, y.astype(float))
    assert perfect["pr_auc"] == pytest.approx(1.0)
    assert perfect["roc_auc"] == pytest.approx(1.0)
    constant = evaluate(y, np.full(100, 0.1))
    assert constant["pr_auc"] == pytest.approx(0.1)
    assert constant["positive_rate"] == pytest.approx(0.1)
    assert set(perfect) == {"pr_auc", "roc_auc", "brier", "log_loss", "precision_at_top",
                            "recall_at_top", "positive_rate"}


def test_precision_at_top():
    y = np.array([1] * 5 + [0] * 95)
    scores = np.linspace(1, 0, 100)
    out = evaluate(y, scores, top_share=0.05)
    assert out["precision_at_top"] == 1.0
    assert out["recall_at_top"] == 1.0


def test_calibration_metrics_use_probabilities_and_ranking_uses_scores():
    y = np.array([0] * 90 + [1] * 10)
    scores = np.linspace(0, 1, 100)
    probs = np.full(100, 0.1)
    out = evaluate(y, scores, y_prob=probs)
    assert out["pr_auc"] == pytest.approx(1.0)
    assert out["brier"] == pytest.approx(evaluate(y, probs)["brier"])


def test_ties_at_the_cutoff_are_not_broken_by_row_order():
    y = np.array([1] * 5 + [0] * 95)
    out = evaluate(y, np.full(100, 0.5), top_share=0.05)
    assert out["precision_at_top"] < 1.0
