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


def _minus_months(d: date, months: int) -> date:
    import calendar

    year, month = divmod(d.year * 12 + (d.month - 1) - months, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def rolling_split_dates(as_of: date) -> tuple[date, date, date]:
    """(train_end, valid_end, test_end) for a retrain run on `as_of`.

    The test window is the 18 months that end a year before `as_of` (so most of its
    contracts have closed); validation is the 6 months before it; training is everything
    earlier.
    """
    from datetime import timedelta

    test_end = as_of - timedelta(days=365)
    valid_end = _minus_months(test_end, 18)
    train_end = _minus_months(valid_end, 6)
    return train_end, valid_end, test_end
