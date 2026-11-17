"""LightGBM risk model with isotonic calibration, tracked in MLflow."""

from __future__ import annotations

import json
from datetime import date
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
                 categories: dict[str, list[str]],
                 feature_names: list[str] | None = None) -> None:
        self.booster = booster
        self.calibrator = calibrator
        self.categories = categories
        # The model's own inputs: a bundle may hold models trained with different lists.
        self.feature_names = list(feature_names or FEATURES)

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        return _prepare(df, self.categories, self.feature_names)

    def predict_raw(self, df: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(self.frame(df))

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return np.clip(self.calibrator.predict(self.predict_raw(df)), 0.0, 1.0)


def _prepare(df: pd.DataFrame, categories: dict[str, list[str]],
             features: list[str] | tuple[str, ...] | None = None) -> pd.DataFrame:
    features = list(features or FEATURES)
    out = df.loc[:, features].copy()
    for col in features:
        if col in CATEGORICAL_FEATURES:
            out[col] = pd.Categorical(out[col].astype("object"), categories=categories[col])
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype(float)
    return out


def train_lightgbm(splits: Splits, target: str, params: dict | None = None) -> RiskModel:
    p = {**DEFAULT_PARAMS, **(params or {})}
    rounds = p.pop("n_estimators")
    features = list(FEATURES)
    categorical = [c for c in features if c in CATEGORICAL_FEATURES]
    categories = {
        col: sorted(splits.train[col].dropna().astype(str).unique().tolist())
        for col in categorical
    }
    x_train = _prepare(splits.train, categories, features)
    x_valid = _prepare(splits.valid, categories, features)
    y_train = splits.train[target].astype(int)
    y_valid = splits.valid[target].astype(int)
    train_set = lgb.Dataset(x_train, y_train, categorical_feature=categorical)
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
    return RiskModel(booster, calibrator, categories, features)


def baseline_scores(splits: Splits, target: str) -> dict[str, np.ndarray]:
    """Test-set scores of the simple baselines, fitted on the training split."""
    scores = {}
    for name, baseline in (("base_rate", BaseRate()), ("buyer_rate", BuyerRate()),
                           ("logistic", LogisticBaseline())):
        baseline.fit(splits.train, target)
        scores[name] = baseline.predict_proba(splits.test)
    return scores


def run_experiment(
    dataset_path: Path,
    target: str,
    tracking_uri: str = "sqlite:///mlflow.db",
    models_dir: Path = Path("data/models"),
    params: dict | None = None,
    figures_dir: Path | None = Path("docs/figures"),
    split_dates: tuple | None = None,
) -> dict[str, dict[str, float]]:
    import mlflow

    df = pd.read_parquet(dataset_path)
    splits = temporal_split(df, *split_dates) if split_dates else temporal_split(df)
    y_test = splits.test[target].astype(int)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(f"amendment-risk-{target}")
    split_sizes = {"n_train": len(splits.train), "n_valid": len(splits.valid),
                   "n_test": len(splits.test)}

    results: dict[str, dict[str, float]] = {}
    scores = baseline_scores(splits, target)
    for name in scores:
        results[name] = evaluate(y_test, scores[name])
        with mlflow.start_run(run_name=name):
            mlflow.log_params({"model": name, "target": target, **split_sizes})
            mlflow.log_metrics({f"test_{k}": v for k, v in results[name].items()})

    model = train_lightgbm(splits, target, params)
    # Ranking metrics on raw scores (isotonic output is tied); probability metrics calibrated.
    raw_test = model.predict_raw(splits.test)
    scores["lightgbm"] = raw_test
    results["lightgbm"] = evaluate(y_test, raw_test, y_prob=model.predict_proba(splits.test))
    model_path = Path(models_dir) / target / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    with mlflow.start_run(run_name="lightgbm"):
        from procurement_risk.model.serving import RiskModelPyfunc

        mlflow.log_params({"model": "lightgbm", "target": target, **split_sizes,
                           "best_iteration": model.booster.best_iteration,
                           **{k: v for k, v in {**DEFAULT_PARAMS, **(params or {})}.items()}})
        mlflow.log_metrics({f"test_{k}": v for k, v in results["lightgbm"].items()})
        mlflow.pyfunc.log_model(
            name="model",
            python_model=RiskModelPyfunc(),
            artifacts={"risk_model": str(model_path)},
            registered_model_name=f"amendment-risk-{target}",
        )

    (model_path.parent / "metrics.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    if figures_dir is not None:
        from procurement_risk.model.report import write_figures

        write_figures(scores, y_test.to_numpy(), model, splits.test, target, figures_dir)
    return results


def dataset_summary(dataset_path: Path, split_dates: tuple | None = None,
                    as_of: date | None = None) -> dict:
    """Summary of the training dataset for the model card; `as_of` is the labelling cutoff."""
    from procurement_risk.model.split import TEST_END, TRAIN_END, VALID_END

    dates = split_dates or (TRAIN_END, VALID_END, TEST_END)
    df = pd.read_parquet(dataset_path, columns=["signed_at", "has_value_addition",
                                                 "has_time_extension"])
    splits = temporal_split(df, *dates)
    signed = pd.to_datetime(df["signed_at"])
    return {
        "n_rows": len(df),
        "signed_from": signed.min().date().isoformat(),
        "signed_to": signed.max().date().isoformat(),
        "positive_rate": {t: float(df[t].astype(float).mean())
                          for t in ("has_value_addition", "has_time_extension")},
        "split_sizes": {"train": len(splits.train), "valid": len(splits.valid),
                        "test": len(splits.test)},
        "split_dates": [d.isoformat() for d in dates],
        **({"as_of": as_of.isoformat()} if as_of else {}),
    }
