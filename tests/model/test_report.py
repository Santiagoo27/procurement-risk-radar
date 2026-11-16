import numpy as np

from procurement_risk.model.report import write_figures, write_model_card
from procurement_risk.model.split import temporal_split
from procurement_risk.model.train import train_lightgbm

RESULTS = {"has_value_addition": {"lightgbm": {"pr_auc": 0.4321, "roc_auc": 0.8, "brier": 0.08,
                                               "log_loss": 0.3, "precision_at_top": 0.5,
                                               "recall_at_top": 0.2, "positive_rate": 0.1},
                                  "base_rate": {"pr_auc": 0.1, "roc_auc": 0.5, "brier": 0.09,
                                                "log_loss": 0.33, "precision_at_top": 0.1,
                                                "recall_at_top": 0.05, "positive_rate": 0.1}}}
SUMMARY = {"n_rows": 1000, "signed_from": "2019-01-01", "signed_to": "2024-12-31",
           "positive_rate": {"has_value_addition": 0.1, "has_time_extension": 0.09},
           "split_sizes": {"train": 600, "valid": 100, "test": 300}}


def test_model_card_contains_disclaimer_and_metrics(tmp_path):
    out = tmp_path / "card.md"
    write_model_card(RESULTS, SUMMARY, out)
    text = out.read_text(encoding="utf-8")
    assert "not allegations of wrongdoing" in text
    assert "0.432" in text
    assert "has_value_addition" in text
    assert "corruption" not in text.lower()


def test_figures_are_written(synthetic, tmp_path):
    splits = temporal_split(synthetic)
    model = train_lightgbm(splits, "has_value_addition",
                           {"n_estimators": 50, "min_child_samples": 20})
    y = splits.test["has_value_addition"].astype(int).to_numpy()
    scores = {"lightgbm": model.predict_proba(splits.test), "base_rate": np.full(len(y), 0.1)}
    paths = write_figures(scores, y, model, splits.test, "has_value_addition", tmp_path)
    assert {p.name for p in paths} == {"has_value_addition-pr-curves.png",
                                       "has_value_addition-calibration.png",
                                       "has_value_addition-importance.png"}
    assert all(p.stat().st_size > 1000 for p in paths)


def test_model_card_describes_labels_as_implemented(tmp_path):
    out = tmp_path / "card.md"
    write_model_card(RESULTS, {**SUMMARY, "as_of": "2026-11-14", "grace_days": 180}, out)
    text = out.read_text(encoding="utf-8")
    assert "or an 'Extension' amendment" in text
    assert "planned end date" in text
    assert "ranking metrics" in text.lower()


def test_model_card_uses_split_dates_from_summary(tmp_path):
    out = tmp_path / "card.md"
    write_model_card(RESULTS, {**SUMMARY, "split_dates": ["2023-11-14", "2024-05-14",
                                                          "2025-11-14"]}, out)
    text = out.read_text(encoding="utf-8")
    assert "train before 2023-11-14" in text and "2024-05-14 to 2025-11-14" in text


def test_model_card_says_which_model_was_kept(tmp_path):
    out = tmp_path / "card.md"
    sources = {"has_value_addition": {"source": "kept", "bundle_version": "model-2026-11-14",
                                      "train_end": "2023-01-01", "data_end": "2025-01-01"}}
    write_model_card(RESULTS, SUMMARY, out, sources=sources)
    text = out.read_text(encoding="utf-8")
    assert "kept from `model-2026-11-14`" in text
    assert "signed before 2023-01-01" in text


def test_model_card_names_features_a_model_does_not_use(tmp_path):
    from procurement_risk.model.train import FEATURES

    out = tmp_path / "card.md"
    older = [f for f in FEATURES if f not in ("signed_in_restriction",
                                              "planned_end_in_restriction",
                                              "days_end_to_next_election")]
    write_model_card(RESULTS, SUMMARY, out, model_features={"has_value_addition": older})
    text = out.read_text(encoding="utf-8")
    assert "does not use: `signed_in_restriction`, `planned_end_in_restriction`" in text
