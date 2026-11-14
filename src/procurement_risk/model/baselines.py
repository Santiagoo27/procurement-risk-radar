"""Baselines the main model has to beat."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES

BUYER_RATE_COLUMN = {
    "has_value_addition": "buyer_prior_value_addition_rate",
    "has_time_extension": "buyer_prior_extension_rate",
}


class BaseRate:
    """Predicts the training positive rate for everyone."""

    def fit(self, train: pd.DataFrame, target: str) -> BaseRate:
        self.rate_ = float(train[target].astype(float).mean())
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return np.full(len(df), self.rate_)


class BuyerRate:
    """Predicts the buyer's point-in-time historical rate."""

    def fit(self, train: pd.DataFrame, target: str) -> BuyerRate:
        self.column_ = BUYER_RATE_COLUMN[target]
        self.fallback_ = float(train[target].astype(float).mean())
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return df[self.column_].fillna(self.fallback_).clip(0, 1).to_numpy(dtype=float)


def _as_str(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.astype("object").where(frame.notna(), "missing").astype(str)


class LogisticBaseline:
    """One-hot categoricals + scaled numerics into a logistic regression."""

    def fit(self, train: pd.DataFrame, target: str) -> LogisticBaseline:
        pre = ColumnTransformer([
            ("cat", make_pipeline(
                _StrCaster(),
                OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50),
            ), list(CATEGORICAL_FEATURES)),
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()),
             list(NUMERIC_FEATURES)),
        ])
        self.pipeline_ = Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=1000))])
        self.pipeline_.fit(train, train[target].astype(int))
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return self.pipeline_.predict_proba(df)[:, 1]


class _StrCaster:
    """Turn categoricals (including NaN) into plain strings for the encoder."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return _as_str(pd.DataFrame(X))

    def get_params(self, deep=True):
        return {}

    def set_params(self, **params):
        return self
