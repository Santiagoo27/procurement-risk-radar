"""Temporal split by signing date (spec 5.2: no random splits across time)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

TRAIN_END = date(2023, 1, 1)
VALID_END = date(2023, 7, 1)
TEST_END = date(2025, 1, 1)


@dataclass
class Splits:
    train: pd.DataFrame
    valid: pd.DataFrame
    test: pd.DataFrame


def temporal_split(
    df: pd.DataFrame,
    train_end: date = TRAIN_END,
    valid_end: date = VALID_END,
    test_end: date = TEST_END,
) -> Splits:
    signed = pd.to_datetime(df["signed_at"])
    t, v, e = (pd.Timestamp(d) for d in (train_end, valid_end, test_end))
    return Splits(
        train=df[signed < t].reset_index(drop=True),
        valid=df[(signed >= t) & (signed < v)].reset_index(drop=True),
        test=df[(signed >= v) & (signed < e)].reset_index(drop=True),
    )
