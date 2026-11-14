"""Per-prediction explanations from LightGBM's built-in SHAP values (pred_contrib)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from procurement_risk.model.train import RiskModel


def contributions(model: RiskModel, df: pd.DataFrame) -> pd.DataFrame:
    """SHAP contribution of each feature to the raw (log-odds) score, plus the bias term."""
    values = model.booster.predict(model.frame(df), pred_contrib=True)
    return pd.DataFrame(values, columns=[*model.feature_names, "bias"], index=df.index)


def top_signals(model: RiskModel, df: pd.DataFrame, k: int = 3) -> list[list[tuple[str, float]]]:
    """For each row, the k features that push risk up the most (positive contributions)."""
    contrib = contributions(model, df).drop(columns="bias")
    values = contrib.to_numpy()
    names = np.asarray(contrib.columns)
    order = np.argsort(-values, axis=1, kind="stable")[:, :k]
    top_values = np.take_along_axis(values, order, axis=1)
    return [
        [(str(names[j]), float(v)) for j, v in zip(row_idx, row_val, strict=True) if v > 0]
        for row_idx, row_val in zip(order, top_values, strict=True)
    ]


def global_importance(model: RiskModel, df: pd.DataFrame) -> pd.Series:
    """Mean absolute contribution per feature, largest first."""
    contrib = contributions(model, df).drop(columns="bias")
    return contrib.abs().mean().sort_values(ascending=False)
