from datetime import date

import numpy as np
import pytest

from procurement_risk.model.split import rolling_split_dates, temporal_split
from procurement_risk.model.train import train_lightgbm
from procurement_risk.ops import promotion
from procurement_risk.ops.promotion import compare, decide, write_report
from procurement_risk.serving.bundle import load_bundle, make_demo_bundle, synthetic_dataset

AS_OF = date(2025, 6, 30)
FAST = {"n_estimators": 60, "min_child_samples": 20}
TARGETS = ("has_value_addition", "has_time_extension")


def test_rolling_split_dates():
    assert rolling_split_dates(date(2026, 11, 14)) == (
        date(2023, 11, 14), date(2024, 5, 14), date(2025, 11, 14))


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    champion = load_bundle(make_demo_bundle(tmp_path_factory.mktemp("b") / "b", seed=0))
    dataset = synthetic_dataset(n=3000, seed=1)
    splits = temporal_split(dataset, *rolling_split_dates(AS_OF))
    challengers = {t: train_lightgbm(splits, t, FAST) for t in TARGETS}
    return champion, dataset, challengers


def test_champion_and_challenger_share_test_rows(setup, monkeypatch):
    champion, dataset, challengers = setup
    seen = []
    real = promotion.evaluate

    def spy(y, score, **kwargs):
        seen.append(np.asarray(y).copy())
        return real(y, score, **kwargs)

    monkeypatch.setattr(promotion, "evaluate", spy)
    result = compare(dataset, champion, challengers, AS_OF)
    assert len(seen) == 4
    assert np.array_equal(seen[0], seen[1]) and np.array_equal(seen[2], seen[3])
    assert result["has_value_addition"]["n_test"] == len(seen[0])
    assert result["has_time_extension"]["n_test"] == len(seen[2])
    for target in TARGETS:
        assert result[target]["test_period"] == ["2022-12-30", "2024-06-30"]


def metrics(pr, brier):
    return {"pr_auc": pr, "brier": brier, "roc_auc": 0.7, "log_loss": 0.3,
            "precision_at_top": 0.3, "recall_at_top": 0.1, "positive_rate": 0.1}


def comparison(ch_va, ch_ext):
    return {
        "has_value_addition": {"champion": metrics(0.24, 0.067), "challenger": ch_va,
                               "n_test": 100, "test_period": ["a", "b"]},
        "has_time_extension": {"champion": metrics(0.32, 0.089), "challenger": ch_ext,
                               "n_test": 100, "test_period": ["a", "b"]},
    }


def test_gate_decides_each_target_on_its_own():
    d = decide(comparison(metrics(0.26, 0.066), metrics(0.28, 0.095)))
    assert d.promote
    assert d.targets == {"has_value_addition": True, "has_time_extension": False}
    assert any("has_time_extension" in r and "keep" in r for r in d.reasons)


def test_gate_keeps_a_target_with_worse_calibration():
    d = decide(comparison(metrics(0.25, 0.080), metrics(0.33, 0.089)))
    assert d.targets == {"has_value_addition": False, "has_time_extension": True}


def test_gate_requires_some_gain():
    d = decide(comparison(metrics(0.2405, 0.067), metrics(0.3205, 0.089)))
    assert not d.promote
    assert d.targets == {"has_value_addition": False, "has_time_extension": False}
    assert any("gain" in r for r in d.reasons)


def test_gate_promotes_better_challenger():
    d = decide(comparison(metrics(0.25, 0.066), metrics(0.322, 0.089)))
    assert d.promote
    assert all(d.targets.values())


def test_report_contains_both_targets_and_decision(tmp_path):
    comp = comparison(metrics(0.25, 0.066), metrics(0.322, 0.089))
    path = tmp_path / "report.md"
    write_report(comp, decide(comp), path)
    text = path.read_text(encoding="utf-8")
    assert "has_value_addition" in text and "has_time_extension" in text
    assert "Promote" in text
    assert "| `has_value_addition` | promote |" in text
    assert "0.240" in text and "0.250" in text


def test_retrain_writes_report_decision_and_models(tmp_path):
    import json

    from procurement_risk.ops.promotion import retrain

    dataset = tmp_path / "ds.parquet"
    synthetic_dataset(n=3000, seed=2).to_parquet(dataset)
    bundle = make_demo_bundle(tmp_path / "bundle", seed=0)
    out = tmp_path / "retrain"
    decision = retrain(dataset, bundle, AS_OF, out, params=FAST)
    saved = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert saved["promote"] == decision.promote
    assert set(saved["comparison"]) == set(TARGETS)
    assert (out / "report.md").exists()
    for target in TARGETS:
        assert (out / "models" / target / "model.joblib").exists()
        assert (out / "models" / target / "metrics.json").exists()


def test_retrain_keeps_the_champion_for_a_target_that_did_not_improve(tmp_path, monkeypatch):
    import json

    import joblib
    import pandas as pd

    from procurement_risk.ops.promotion import Decision, retrain

    def mixed(comp, gate=None):
        return Decision(promote=True, targets={"has_value_addition": True,
                                               "has_time_extension": False},
                        reasons=["mixed"])

    monkeypatch.setattr(promotion, "decide", mixed)
    dataset = tmp_path / "ds.parquet"
    synthetic_dataset(n=3000, seed=2).to_parquet(dataset)
    bundle = make_demo_bundle(tmp_path / "bundle", seed=0)
    champion = load_bundle(bundle)
    out = tmp_path / "retrain"
    retrain(dataset, bundle, AS_OF, out, params=FAST)

    final = out / "final_models"
    df = pd.read_parquet(dataset)
    kept = joblib.load(final / "has_time_extension" / "model.joblib")
    assert np.allclose(kept.predict_raw(df),
                       champion.models["has_time_extension"].predict_raw(df))
    new = joblib.load(final / "has_value_addition" / "model.joblib")
    challenger = joblib.load(out / "models" / "has_value_addition" / "model.joblib")
    assert np.allclose(new.predict_raw(df), challenger.predict_raw(df))

    saved = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert saved["targets"] == {"has_value_addition": True, "has_time_extension": False}
    ext_metrics = json.loads((final / "has_time_extension" / "metrics.json")
                             .read_text(encoding="utf-8"))
    assert ext_metrics["lightgbm"] == saved["comparison"]["has_time_extension"]["champion"]
    assert "logistic" in ext_metrics
    sources = {t: json.loads((final / t / "source.json").read_text(encoding="utf-8"))
               for t in TARGETS}
    assert sources["has_value_addition"]["source"] == "retrained"
    assert sources["has_value_addition"]["data_end"] == "2024-06-30"
    assert sources["has_time_extension"] == {
        "source": "kept", "bundle_version": "demo", "train_end": "2023-01-01",
        "data_end": "2025-01-01"}
    for target in TARGETS:
        assert (out / "figures" / f"{target}-pr-curves.png").exists()

    from procurement_risk import __main__ as cli

    card = tmp_path / "card.md"
    cli.main(["model-card", "--dataset", str(dataset), "--models", str(final),
              "--out", str(card), "--rolling-as-of", AS_OF.isoformat()])
    assert "kept from `demo`" in card.read_text(encoding="utf-8")
