"""LightGBM risk model with isotonic calibration, tracked in MLflow."""

from __future__ import annotations

from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from procurement_risk.model.baselines import BaseRate, BuyerRate, LogisticBaseline
from procurement_risk.model.metrics import evaluate
from procurement_risk.model.split import Splits, temporal_split

FEATURES: tuple[str, ...] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

DEFAULT_PARAMS = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 100,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "n_estimators": 2000,
    "verbosity": -1,
    "seed": 42,
}
EARLY_STOPPING_ROUNDS = 100


class RiskModel:
    """Booster + calibrator + the categorical vocabulary fixed at training time."""

    def __init__(self, booster: lgb.Booster, calibrator: IsotonicRegression,
                 categories: dict[str, list[str]]) -> None:
        self.booster = booster
        self.calibrator = calibrator
        self.categories = categories
        self.feature_names = list(FEATURES)

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        return _prepare(df, self.categories)

    def predict_raw(self, df: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(self.frame(df))

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(self.calibrator.predict(self.predict_raw(df)), 0.0, 1.0)


def _prepare(df: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    out = df.loc[:, list(FEATURES)].copy()
    for col in CATEGORICAL_FEATURES:
        out[col] = pd.Categorical(out[col].astype("object"), categories=categories[col])
    for col in NUMERIC_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(float)
    return out


def train_lightgbm(splits: Splits, target: str, params: dict | None = None) -> RiskModel:
    p = {**DEFAULT_PARAMS, **(params or {})}
    rounds = p.pop("n_estimators")
    categories = {
        col: sorted(splits.train[col].dropna().astype(str).unique().tolist())
        for col in CATEGORICAL_FEATURES
    }
    x_train, x_valid = _prepare(splits.train, categories), _prepare(splits.valid, categories)
    y_train = splits.train[target].astype(int)
    y_valid = splits.valid[target].astype(int)
    train_set = lgb.Dataset(x_train, y_train, categorical_feature=list(CATEGORICAL_FEATURES))
    valid_set = lgb.Dataset(x_valid, y_valid, reference=train_set)
    booster = lgb.train(
        {**p, "metric": "average_precision"},
        train_set,
        num_boost_round=rounds,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
    )
    # Calibration uses the validation period only; the test period stays untouched.
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(booster.predict(x_valid), y_valid)
    return RiskModel(booster, calibrator, categories)


def run_experiment(
    dataset_path: Path,
    target: str,
    tracking_uri: str = "sqlite:///mlflow.db",
    models_dir: Path = Path("data/models"),
    params: dict | None = None,
    figures_dir: Path | None = Path("docs/figures"),
) -> dict[str, dict[str, float]]:
    import mlflow

    df = pd.read_parquet(dataset_path)
    splits = temporal_split(df)
    y_test = splits.test[target].astype(int)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(f"amendment-risk-{target}")
    split_sizes = {"n_train": len(splits.train), "n_valid": len(splits.valid),
                   "n_test": len(splits.test)}

    results: dict[str, dict[str, float]] = {}
    scores: dict[str, np.ndarray] = {}
    for name, baseline in (("base_rate", BaseRate()), ("buyer_rate", BuyerRate()),
                           ("logistic", LogisticBaseline())):
        baseline.fit(splits.train, target)
        scores[name] = baseline.predict_proba(splits.test)
        results[name] = evaluate(y_test, scores[name])
        with mlflow.start_run(run_name=name):
            mlflow.log_params({"model": name, "target": target, **split_sizes})
            mlflow.log_metrics({f"test_{k}": v for k, v in results[name].items()})

    model = train_lightgbm(splits, target, params)
    scores["lightgbm"] = model.predict_proba(splits.test)
    results["lightgbm"] = evaluate(y_test, scores["lightgbm"])
    model_path = Path(models_dir) / target / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    with mlflow.start_run(run_name="lightgbm"):
        mlflow.log_params({"model": "lightgbm", "target": target, **split_sizes,
                           "best_iteration": model.booster.best_iteration,
                           **{k: v for k, v in {**DEFAULT_PARAMS, **(params or {})}.items()}})
        mlflow.log_metrics({f"test_{k}": v for k, v in results["lightgbm"].items()})
        mlflow.lightgbm.log_model(model.booster, name="model",
                                  registered_model_name=f"amendment-risk-{target}")
        mlflow.log_artifact(str(model_path), artifact_path="calibrated")

    run_experiment.last = (model, splits, scores)  # for reporting (Task 7)
    return results
