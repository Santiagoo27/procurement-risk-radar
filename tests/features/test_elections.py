from datetime import date, timedelta

import pandas as pd
import pytest

from procurement_risk.features.elections import ELECTION_DAYS, RESTRICTION_DAYS
from procurement_risk.serving.bundle import load_bundle, make_demo_bundle
from procurement_risk.serving.scoring import features_for

COLS = ["signed_in_restriction", "planned_end_in_restriction", "days_end_to_next_election"]


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return load_bundle(make_demo_bundle(tmp_path_factory.mktemp("b") / "b"))


def features(bundle, **contract):
    return features_for(bundle, [{"buyer_id": "DEMO-A", **contract}])[COLS].iloc[0]


def test_calendar_matches_known_election_days():
    known = {date(2018, 3, 11), date(2018, 5, 27), date(2019, 10, 27), date(2022, 3, 13),
             date(2022, 5, 29), date(2023, 10, 29), date(2026, 3, 8), date(2026, 5, 31),
             date(2027, 10, 31)}
    assert known <= set(ELECTION_DAYS)
    assert [d for d in ELECTION_DAYS if d.year <= 2027] == sorted(known)
    assert RESTRICTION_DAYS == 122


def test_calendar_covers_the_next_year():
    # When this fails, extend election_days() past its last year.
    assert max(ELECTION_DAYS) >= date.today() + timedelta(days=365)


def test_signed_inside_a_restriction_window(bundle):
    row = features(bundle, signed_at="2023-08-01", planned_start_at="2023-08-01",
                   planned_duration_days=30)
    assert row["signed_in_restriction"] == 1


def test_planned_end_inside_a_restriction_window(bundle):
    # 2023-01-10 + 200 days = 2023-07-29, 92 days before the 2023-10-29 regional elections
    row = features(bundle, signed_at="2023-01-10", planned_start_at="2023-01-10",
                   planned_duration_days=200)
    assert row["signed_in_restriction"] == 0
    assert row["planned_end_in_restriction"] == 1
    assert row["days_end_to_next_election"] == 92


def test_outside_any_window(bundle):
    row = features(bundle, signed_at="2024-03-01", planned_start_at="2024-03-01",
                   planned_duration_days=30)
    assert row["signed_in_restriction"] == 0
    assert row["planned_end_in_restriction"] == 0


def test_missing_start_falls_back_to_signing(bundle):
    row = features(bundle, signed_at="2023-01-10", planned_duration_days=200)
    assert row["days_end_to_next_election"] == 92


def test_missing_duration_gives_null_end_features(bundle):
    row = features(bundle, signed_at="2023-01-10", planned_start_at="2023-01-10")
    assert pd.isna(row["planned_end_in_restriction"])
    assert pd.isna(row["days_end_to_next_election"])


def test_after_the_calendar_gives_null(bundle):
    row = features(bundle, signed_at="2041-01-01", planned_start_at="2041-01-01",
                   planned_duration_days=30)
    assert row.isna().all()
