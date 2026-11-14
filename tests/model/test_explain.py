import numpy as np
import pytest

from procurement_risk.model.explain import contributions, global_importance, top_signals
from procurement_risk.model.split import temporal_split
from procurement_risk.model.train import train_lightgbm


@pytest.fixture
def fitted(synthetic):
    splits = temporal_split(synthetic)
    return train_lightgbm(splits, "has_value_addition",
                          {"n_estimators": 100, "min_child_samples": 20}), splits.test


def test_contributions_sum_to_raw_score(fitted):
    model, test = fitted
    contrib = contributions(model, test)
    assert list(contrib.columns) == model.feature_names + ["bias"]
    raw = model.booster.predict(model.frame(test), raw_score=True)
    assert np.allclose(contrib.sum(axis=1).to_numpy(), raw, atol=1e-6)


def test_top_signals_returns_k_positive_features(fitted):
    model, test = fitted
    signals = top_signals(model, test.head(20), k=3)
    assert len(signals) == 20
    for row in signals:
        assert len(row) <= 3
        assert all(value > 0 for _, value in row)
        assert all(name in model.feature_names for name, _ in row)
        assert [v for _, v in row] == sorted((v for _, v in row), reverse=True)


def test_global_importance_ranks_signal_feature_first(fitted):
    model, test = fitted
    assert global_importance(model, test).index[0] == "log_award_value"
