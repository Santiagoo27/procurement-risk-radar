"""Champion vs challenger: same test rows, explicit gate, a report for the owner's PR."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from procurement_risk.model.metrics import evaluate
from procurement_risk.model.split import rolling_split_dates, temporal_split
from procurement_risk.model.train import RiskModel
from procurement_risk.ops.config import PromotionGate
from procurement_risk.serving.bundle import Bundle

TARGETS = ("has_value_addition", "has_time_extension")


def _score(model: RiskModel, frame: pd.DataFrame, y) -> dict[str, float]:
    return evaluate(y, model.predict_raw(frame), y_prob=model.predict_proba(frame))


def compare(dataset: pd.DataFrame, champion: Bundle, challengers: dict[str, RiskModel],
            as_of: date) -> dict:
    """Score the production (champion) and new (challenger) models on identical test rows."""
    train_end, valid_end, test_end = rolling_split_dates(as_of)
    test = temporal_split(dataset, train_end, valid_end, test_end).test
    result = {}
    for target in TARGETS:
        y = test[target].astype(int).to_numpy()
        result[target] = {
            "champion": _score(champion.models[target], test, y),
            "challenger": _score(challengers[target], test, y),
            "n_test": int(len(test)),
            "test_period": [valid_end.isoformat(), test_end.isoformat()],
        }
    return result


@dataclass
class Decision:
    promote: bool
    targets: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def decide(comparison: dict, gate: PromotionGate | None = None) -> Decision:
    """Each target on its own: its new model replaces the production one only if it gains
    PR-AUC and keeps calibration. A target that does not improve keeps its current model, so
    a bad retrain for one target never blocks a good one for the other."""
    from procurement_risk.ops import config

    g = gate or config.GATE
    targets: dict[str, bool] = {}
    reasons: list[str] = []
    for target, row in comparison.items():
        champ, chall = row["champion"], row["challenger"]
        gain = chall["pr_auc"] - champ["pr_auc"]
        problems = []
        if gain < g.min_pr_auc_gain:
            problems.append(f"PR-AUC gain {gain:+.3f} is below {g.min_pr_auc_gain}")
        if chall["brier"] > champ["brier"] * g.max_brier_ratio:
            problems.append(f"Brier score worsened from {champ['brier']:.4f} to "
                            f"{chall['brier']:.4f} (allowed +{g.max_brier_ratio - 1:.0%})")
        targets[target] = not problems
        if problems:
            reasons.append(f"{target}: keep the current model; " + "; ".join(problems))
        else:
            reasons.append(f"{target}: promote; PR-AUC {gain:+.3f}, Brier "
                           f"{champ['brier']:.4f} to {chall['brier']:.4f}")
    return Decision(promote=any(targets.values()), targets=targets, reasons=reasons)


def write_report(comparison: dict, decision: Decision, path: Path) -> None:
    if not decision.promote:
        verdict = "Keep the current models"
    elif all(decision.targets.values()):
        verdict = "Promote the new models"
    else:
        verdict = "Promote some of the new models"
    lines = [f"## Monthly retrain: {verdict}", "",
             "| Target | Decision |", "|---|---|",
             *[f"| `{t}` | {'promote' if ok else 'keep current'} |"
               for t, ok in decision.targets.items()], ""]
    for target, row in comparison.items():
        lines += [
            f"### `{target}`",
            "",
            f"Test period {row['test_period'][0]} to {row['test_period'][1]}, "
            f"{row['n_test']:,} contracts (same rows for both models).",
            "",
            "| Metric | Current (champion) | New (challenger) | Change |",
            "|---|---:|---:|---:|",
        ]
        for metric in ("pr_auc", "roc_auc", "brier", "precision_at_top"):
            a, b = row["champion"][metric], row["challenger"][metric]
            lines.append(f"| {metric} | {a:.3f} | {b:.3f} | {b - a:+.3f} |")
        lines.append("")
    lines += ["### Decision", "", *[f"- {r}" for r in decision.reasons], ""]
    if decision.promote:
        lines += [
            "### How to approve",
            "",
            "1. Publish the draft release linked in this PR (Releases → Edit → Publish).",
            "2. Merge this PR. Render rebuilds the API with the new bundle; the next weekly "
            "refresh rescores the website with it.",
            "",
        ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def retrain(dataset_path: Path, bundle_dir: Path, as_of: date, out_dir: Path,
            params: dict | None = None) -> Decision:
    """Train challengers on a rolling split, compare them with the production bundle and
    write report.md, decision.json and the challenger models (ready for export-bundle)."""
    import json

    import joblib

    from procurement_risk.model.train import run_experiment
    from procurement_risk.serving.bundle import load_bundle

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = rolling_split_dates(as_of)
    uri = f"sqlite:///{(out_dir / 'mlflow.db').resolve().as_posix()}"
    challengers = {}
    for target in TARGETS:
        run_experiment(Path(dataset_path), target, tracking_uri=uri,
                       models_dir=out_dir / "models", params=params,
                       figures_dir=out_dir / "figures", split_dates=dates)
        challengers[target] = joblib.load(out_dir / "models" / target / "model.joblib")

    dataset = pd.read_parquet(dataset_path)
    champion = load_bundle(bundle_dir)
    comparison = compare(dataset, champion, challengers, as_of)
    decision = decide(comparison)
    write_report(comparison, decision, out_dir / "report.md")
    (out_dir / "decision.json").write_text(json.dumps({
        "as_of": as_of.isoformat(), "promote": decision.promote, "targets": decision.targets,
        "reasons": decision.reasons, "split_dates": [d.isoformat() for d in dates],
        "comparison": comparison,
    }, indent=2), encoding="utf-8")
    if decision.promote:  # nothing ships otherwise, so skip redrawing kept models' figures
        _assemble_final_models(out_dir, dataset, champion, comparison, decision, dates)
    return decision


def _assemble_final_models(out_dir: Path, dataset: pd.DataFrame, champion: Bundle,
                           comparison: dict, decision: Decision, dates: tuple) -> None:
    """Write `final_models/<target>/` with the model each target will ship: the new one if it
    was promoted, otherwise the production one. Each gets the metrics.json the model card and
    bundle read, and a source.json recording where it came from. For a kept model the metrics
    are its scores on this retrain's test rows (baselines refit on this split) and its
    figures are redrawn on those rows, so the card describes the model that ships."""
    import json
    import shutil

    import joblib

    from procurement_risk.model.report import write_figures
    from procurement_risk.model.train import baseline_scores

    final = out_dir / "final_models"
    if final.exists():
        shutil.rmtree(final)
    train_end, _, test_end = dates
    meta = champion.metadata
    for target, promoted in decision.targets.items():
        dest = final / target
        dest.mkdir(parents=True)
        if promoted:
            shutil.copytree(out_dir / "models" / target, dest, dirs_exist_ok=True)
            source = {"source": "retrained", "train_end": train_end.isoformat(),
                      "data_end": test_end.isoformat()}
        else:
            joblib.dump(champion.models[target], dest / "model.joblib")
            metrics = json.loads((out_dir / "models" / target / "metrics.json")
                                 .read_text(encoding="utf-8"))
            metrics["lightgbm"] = comparison[target]["champion"]
            (dest / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            # A model kept through several months keeps its original training window.
            earlier = meta.get("model_sources", {}).get(target, {})
            source = {"source": "kept",
                      "bundle_version": earlier.get("bundle_version",
                                                    meta.get("bundle_version")),
                      "train_end": earlier.get("train_end", meta.get("train_end", "2023-01-01")),
                      "data_end": earlier.get("data_end", meta.get("data_end", "2025-01-01"))}
            splits = temporal_split(dataset, *dates)
            model = champion.models[target]
            scores = {**baseline_scores(splits, target), "lightgbm": model.predict_raw(splits.test)}
            write_figures(scores, splits.test[target].astype(int).to_numpy(), model, splits.test,
                          target, out_dir / "figures")
        (dest / "source.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
