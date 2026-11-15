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
    reasons: list[str] = field(default_factory=list)


def decide(comparison: dict, gate: PromotionGate | None = None) -> Decision:
    from procurement_risk.ops import config

    g = gate or config.GATE
    reasons: list[str] = []
    ok = True
    best_gain = float("-inf")
    for target, row in comparison.items():
        champ, chall = row["champion"], row["challenger"]
        gain = chall["pr_auc"] - champ["pr_auc"]
        best_gain = max(best_gain, gain)
        if gain < -g.max_pr_auc_drop:
            ok = False
            reasons.append(f"{target}: PR-AUC fell by {-gain:.3f} (allowed {g.max_pr_auc_drop})")
        if chall["brier"] > champ["brier"] * g.max_brier_ratio:
            ok = False
            reasons.append(f"{target}: Brier score worsened from {champ['brier']:.4f} to "
                           f"{chall['brier']:.4f}")
    if best_gain < g.min_pr_auc_gain:
        ok = False
        reasons.append(f"no target gains at least {g.min_pr_auc_gain} PR-AUC "
                       f"(best gain {best_gain:+.3f})")
    if ok:
        reasons.append("challenger is at least as good on both targets and better on one")
    return Decision(promote=ok, reasons=reasons)


def write_report(comparison: dict, decision: Decision, path: Path) -> None:
    verdict = "Promote the new model" if decision.promote else "Keep the current model"
    lines = [f"## Monthly retrain: {verdict}", ""]
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

    comparison = compare(pd.read_parquet(dataset_path), load_bundle(bundle_dir), challengers,
                         as_of)
    decision = decide(comparison)
    write_report(comparison, decision, out_dir / "report.md")
    (out_dir / "decision.json").write_text(json.dumps({
        "as_of": as_of.isoformat(), "promote": decision.promote, "reasons": decision.reasons,
        "split_dates": [d.isoformat() for d in dates], "comparison": comparison,
    }, indent=2), encoding="utf-8")
    return decision
