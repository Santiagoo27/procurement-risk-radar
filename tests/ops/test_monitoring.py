from datetime import date

import numpy as np
import pandas as pd
import pytest

from procurement_risk.ops.monitoring import build_report, psi
from procurement_risk.serving.bundle import load_bundle, make_demo_bundle, synthetic_dataset

RNG = np.random.default_rng(0)


def test_psi_zero_for_identical_distributions():
    x = pd.Series(RNG.normal(size=5000))
    assert psi(x, x.copy()) == pytest.approx(0.0, abs=1e-9)


def test_psi_detects_shift():
    ref = pd.Series(RNG.normal(size=5000))
    cur = pd.Series(RNG.normal(loc=1.0, size=5000))
    assert psi(ref, cur) > 0.2


def test_psi_categorical():
    ref = pd.Series(["a"] * 900 + ["b"] * 100)
    cur = pd.Series(["a"] * 500 + ["b"] * 500)
    assert psi(ref, cur) > 0.2
    assert psi(ref, ref.copy()) == pytest.approx(0.0, abs=1e-9)


def test_psi_none_for_tiny_windows():
    assert psi(pd.Series(RNG.normal(size=5000)), pd.Series(RNG.normal(size=100))) is None
    assert psi(pd.Series([np.nan] * 600), pd.Series(RNG.normal(size=600))) is None


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return load_bundle(make_demo_bundle(tmp_path_factory.mktemp("b") / "b"))


def frame(n, start, days, closed=True, seed=0):
    df = synthetic_dataset(n=n, seed=seed)
    rng = np.random.default_rng(seed)
    df["signed_at"] = pd.Timestamp(start) + pd.to_timedelta(rng.integers(0, days, n), unit="D")
    df["is_closed"] = closed
    return df


def test_report_status_insufficient_data(bundle):
    reference = frame(3000, "2021-01-01", 700)
    report = build_report(reference, bundle, date(2026, 11, 14),
                          reference_end=date(2023, 1, 1), data_end=date(2025, 1, 1))
    assert report["status"] == "insufficient_data"
    assert all(f["psi"] is None for f in report["feature_drift"])
    assert report["realized"]["pr_auc"] is None and report["realized"]["reason"]


def test_report_flags_shifted_feature(bundle):
    reference = frame(3000, "2021-01-01", 700, seed=1)
    current = frame(1500, "2026-09-01", 70, closed=False, seed=2)
    current["log_award_value"] += 2.0
    report = build_report(pd.concat([reference, current], ignore_index=True), bundle,
                          date(2026, 11, 14), reference_end=date(2023, 1, 1),
                          data_end=date(2025, 1, 1))
    assert report["status"] == "watch"
    top = report["feature_drift"][0]
    assert top["feature"] == "log_award_value" and top["shifted"] is True
    assert top["label"] == "Awarded value"
    assert report["score_shift"]["current_mean"] is not None
    assert report["windows"]["current"] == ["2026-08-16", "2026-11-14"]


def test_calendar_and_cumulative_features_are_expected_drift(bundle):
    reference = frame(3000, "2021-01-01", 700, seed=1)
    current = frame(1500, "2026-09-01", 70, closed=False, seed=2)
    current["signing_month"] = 10
    report = build_report(pd.concat([reference, current], ignore_index=True), bundle,
                          date(2026, 11, 14), reference_end=date(2023, 1, 1),
                          data_end=date(2025, 1, 1))
    month = next(d for d in report["feature_drift"] if d["feature"] == "signing_month")
    assert month["expected"] is True and month["shifted"] is False
    assert report["status"] == "ok"


def test_realized_uses_only_contracts_with_complete_inputs(bundle):
    reference = frame(3000, "2021-01-01", 700, seed=1)
    late = frame(1200, "2025-02-01", 300, closed=True, seed=3)
    late["process_found"] = [True] * 600 + [False] * 600
    report = build_report(pd.concat([reference, late], ignore_index=True), bundle,
                          date(2026, 11, 14), reference_end=date(2023, 1, 1),
                          data_end=date(2025, 1, 1))
    assert report["realized"]["n"] == 600


def test_realized_alert_uses_roc_auc_not_pr_auc(bundle, monkeypatch):
    from procurement_risk.ops import monitoring

    reference = frame(3000, "2021-01-01", 700, seed=1)
    late = frame(1200, "2025-02-01", 300, closed=True, seed=3)
    late["process_found"] = True

    def fake_evaluate(y, score, **kwargs):
        return {"pr_auc": 0.9, "roc_auc": 0.40, "positive_rate": 0.5}

    monkeypatch.setattr(monitoring, "evaluate", fake_evaluate)
    report = build_report(pd.concat([reference, late], ignore_index=True), bundle,
                          date(2026, 11, 14), reference_end=date(2023, 1, 1),
                          data_end=date(2025, 1, 1))
    assert report["realized"]["roc_auc"] == 0.40
    assert report["status"] == "watch"


def test_realized_ignores_rows_without_labels(bundle):
    reference = frame(3000, "2021-01-01", 700, seed=1)
    late = frame(1200, "2025-02-01", 300, closed=True, seed=3)
    late["process_found"] = True
    late["has_value_addition"] = late["has_value_addition"].astype(object)
    late.loc[late.index[:100], "has_value_addition"] = None
    report = build_report(pd.concat([reference, late], ignore_index=True), bundle,
                          date(2026, 11, 14), reference_end=date(2023, 1, 1),
                          data_end=date(2025, 1, 1))
    assert report["realized"]["n"] == 1100
