import numpy as np
import pytest
from sklearn.isotonic import IsotonicRegression

from procurement_risk.model.baselines import BaseRate
from procurement_risk.model.metrics import evaluate
from procurement_risk.model.split import temporal_split
from procurement_risk.model.train import run_experiment, train_lightgbm

FAST = {"n_estimators": 200, "min_child_samples": 20}


def test_lightgbm_beats_base_rate_on_synthetic(synthetic):
    splits = temporal_split(synthetic)
    model = train_lightgbm(splits, "has_value_addition", FAST)
    y = splits.test["has_value_addition"]
    lgb_pr = evaluate(y, model.predict_proba(splits.test))["pr_auc"]
    base = BaseRate().fit(splits.train, "has_value_addition").predict_proba(splits.test)
    assert lgb_pr > evaluate(y, base)["pr_auc"] + 0.1


def test_calibrator_sees_only_validation_rows(synthetic, monkeypatch):
    seen = []
    original = IsotonicRegression.fit

    def spy(self, X, y, *args, **kwargs):
        seen.append(len(X))
        return original(self, X, y, *args, **kwargs)

    monkeypatch.setattr(IsotonicRegression, "fit", spy)
    splits = temporal_split(synthetic)
    train_lightgbm(splits, "has_value_addition", FAST)
    assert seen == [len(splits.valid)]


def test_calibrated_probabilities_in_unit_interval(synthetic):
    splits = temporal_split(synthetic)
    model = train_lightgbm(splits, "has_value_addition", FAST)
    p = model.predict_proba(splits.test)
    assert ((p >= 0) & (p <= 1)).all()
    assert model.predict_raw(splits.test).shape == p.shape


def test_unseen_category_does_not_crash(synthetic):
    splits = temporal_split(synthetic)
    model = train_lightgbm(splits, "has_value_addition", FAST)
    df = splits.test.head(3).copy()
    df["contract_type"] = "brand new type"
    assert np.isfinite(model.predict_proba(df)).all()


def test_run_experiment_logs_to_mlflow(synthetic, tmp_path):
    import mlflow

    ds = tmp_path / "ds.parquet"
    synthetic.to_parquet(ds)
    uri = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    results = run_experiment(ds, "has_value_addition", tracking_uri=uri,
                             models_dir=tmp_path / "models", params=FAST,
                             figures_dir=tmp_path / "figures")
    assert set(results) == {"base_rate", "buyer_rate", "logistic", "lightgbm"}
    client = mlflow.MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name("amendment-risk-has_value_addition")
    runs = client.search_runs([exp.experiment_id])
    assert {r.info.run_name for r in runs} == set(results)
    versions = client.search_model_versions("name='amendment-risk-has_value_addition'")
    assert len(versions) == 1
    assert (tmp_path / "models" / "has_value_addition" / "model.joblib").exists()
    assert results["lightgbm"]["pr_auc"] == pytest.approx(
        next(r for r in runs if r.info.run_name == "lightgbm").data.metrics["test_pr_auc"])
