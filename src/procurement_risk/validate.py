"""Checks a training dataset must pass before it is written or used."""

from __future__ import annotations

import pandas as pd

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGETS

FORBIDDEN_COLUMNS = ("valor_del_contrato", "current_end_at", "added_days", "estado_contrato",
                     "supplier_key", "proveedor_adjudicado")
RATE_RANGE = (0.005, 0.6)


class DatasetValidationError(ValueError):
    """The dataset is not safe or plausible enough to train on."""


def validate_dataset(df: pd.DataFrame) -> None:
    problems: list[str] = []
    forbidden = [c for c in FORBIDDEN_COLUMNS if c in df.columns]
    if forbidden:
        problems.append(f"forbidden columns present: {forbidden}")
    dupes = int(df["contract_id"].duplicated().sum())
    if dupes:
        problems.append(f"{dupes} duplicate contract_id rows")
    for col in CATEGORICAL_FEATURES + NUMERIC_FEATURES:
        if col not in df.columns:
            problems.append(f"missing feature column {col}")
        elif df[col].isna().all():
            problems.append(f"feature {col} is 100% null")
    low, high = RATE_RANGE
    for target in TARGETS:
        rate = float(df[target].astype(float).mean())
        if not low <= rate <= high:
            problems.append(f"{target} rate {rate:.3f} outside [{low}, {high}]")
    if problems:
        raise DatasetValidationError("; ".join(problems))
