import numpy as np

from procurement_risk.model.baselines import BaseRate, BuyerRate, LogisticBaseline


def test_base_rate_is_constant_train_rate(synthetic):
    model = BaseRate().fit(synthetic, "has_value_addition")
    pred = model.predict_proba(synthetic.head(10))
    assert np.allclose(pred, synthetic["has_value_addition"].mean())


def test_buyer_rate_reads_point_in_time_column(synthetic):
    pred = BuyerRate().fit(synthetic, "has_time_extension").predict_proba(synthetic)
    assert np.allclose(pred, synthetic["buyer_prior_extension_rate"].clip(0, 1))


def test_logistic_baseline_handles_unseen_category(synthetic):
    model = LogisticBaseline().fit(synthetic, "has_value_addition")
    unseen = synthetic.head(5).copy()
    unseen["procurement_method"] = "never seen"
    unseen.loc[unseen.index[0], "n_bidders"] = np.nan
    pred = model.predict_proba(unseen)
    assert pred.shape == (5,)
    assert ((pred >= 0) & (pred <= 1)).all()
