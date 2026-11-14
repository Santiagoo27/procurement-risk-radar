"""Evaluation figures and the model card. Figures show aggregates only."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import precision_recall_curve  # noqa: E402

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES  # noqa: E402
from procurement_risk.model.explain import global_importance  # noqa: E402
from procurement_risk.model.train import RiskModel  # noqa: E402

DISCLAIMER = (
    "Scores are statistical estimates for analysis, not allegations of wrongdoing. "
    "They estimate the chance that a contract will be amended, nothing more."
)
MODEL_LABELS = {"base_rate": "Base rate", "buyer_rate": "Buyer history rate",
                "logistic": "Logistic regression", "lightgbm": "LightGBM (calibrated)"}
TARGET_LABELS = {"has_value_addition": "value addition", "has_time_extension": "time extension"}


def write_figures(scores: dict[str, np.ndarray], y_true: np.ndarray, model: RiskModel,
                  test_df: pd.DataFrame, target: str, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = TARGET_LABELS.get(target, target)
    paths = []

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for name, s in scores.items():
        precision, recall, _ = precision_recall_curve(y_true, s)
        ax.plot(recall, precision, label=MODEL_LABELS.get(name, name))
    ax.set(xlabel="Recall", ylabel="Precision", title=f"Precision-recall, {label} (test)")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    paths.append(_save(fig, out_dir / f"{target}-pr-curves.png"))

    raw = model.predict_raw(test_df)
    calibrated = model.predict_proba(test_df)
    fig, ax = plt.subplots(figsize=(5, 5))
    for name, s in (("Raw LightGBM", raw), ("Calibrated", calibrated)):
        bins = pd.qcut(s, 10, labels=False, duplicates="drop")
        frame = pd.DataFrame({"s": s, "y": y_true, "b": bins}).groupby("b").mean()
        ax.plot(frame["s"], frame["y"], marker="o", label=name)
    lim = max(float(np.max(calibrated)), float(np.max(raw)), 0.05)
    ax.plot([0, lim], [0, lim], linestyle="--", color="grey", label="Perfect calibration")
    ax.set(xlabel="Predicted probability", ylabel="Observed rate",
           title=f"Calibration, {label} (test, deciles)")
    ax.legend(frameon=False)
    ax.grid(alpha=0.3)
    paths.append(_save(fig, out_dir / f"{target}-calibration.png"))

    importance = global_importance(model, test_df).head(15)[::-1]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.barh(importance.index, importance.to_numpy())
    ax.set(xlabel="Mean |SHAP contribution| (log-odds)",
           title=f"Top features, {label} (test)")
    ax.grid(alpha=0.3, axis="x")
    paths.append(_save(fig, out_dir / f"{target}-importance.png"))
    return paths


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _metrics_table(results: dict[str, dict[str, float]]) -> list[str]:
    lines = ["| Model | PR-AUC | ROC-AUC | Brier | Log loss | Precision @ top 5% | "
             "Recall @ top 5% |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, m in results.items():
        lines.append(
            f"| {MODEL_LABELS.get(name, name)} | {m['pr_auc']:.3f} | {m['roc_auc']:.3f} | "
            f"{m['brier']:.4f} | {m['log_loss']:.4f} | {m['precision_at_top']:.3f} | "
            f"{m['recall_at_top']:.3f} |")
    return lines


def write_model_card(all_results: dict[str, dict[str, dict[str, float]]], summary: dict,
                     out_path: Path) -> None:
    rates = summary["positive_rate"]
    sizes = summary["split_sizes"]
    lines = [
        "# Model card: amendment risk at signing time",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Intended use",
        "",
        "Estimate, at the moment a Colombian public contract is signed, the probability that it",
        "will later receive a value addition (primary target) or a time extension (secondary",
        "target), to help analysts, journalists and oversight bodies prioritise review. Not for",
        "decisions about individual people or suppliers.",
        "",
        "## Data",
        "",
        "- Source: SECOP II open data (datos.gov.co), contracts signed "
        f"{summary['signed_from']} to {summary['signed_to']}; "
        f"{summary['n_rows']:,} closed contracts.",
        "- Closed contract: current end date at least 180 days before 2026-11-14. Only closed "
        "contracts are labelled.",
        f"- `has_value_addition` ({rates['has_value_addition']:.1%} positive): an explicit "
        "'Adicion en el valor' amendment, or a generic amendment whose text describes a value "
        "addition (see [data audit](data-audit.md)).",
        f"- `has_time_extension` ({rates['has_time_extension']:.1%} positive): added days > 0.",
        f"- Temporal split by signing date: train before 2023-01-01 ({sizes['train']:,}), "
        f"validation 2023-H1 ({sizes['valid']:,}), test 2023-07-01 to 2024-12-31 "
        f"({sizes['test']:,}).",
        "",
        "## Features",
        "",
        "Only information known at signing time.",
        "",
        f"- Categorical: {', '.join(f'`{c}`' for c in CATEGORICAL_FEATURES)}.",
        f"- Numeric: {', '.join(f'`{c}`' for c in NUMERIC_FEATURES)}.",
        "- Buyer and supplier history use only labels observable before the signing date "
        "(end date + 180 days), smoothed toward the training-period rate.",
        "- Excluded: current contract value (already includes additions), current end date and "
        "stated duration (moved by extensions), added days, contract status (stale), payments, "
        "identifiers and supplier names.",
        "",
        "## Evaluation (test split)",
        "",
    ]
    for target, results in all_results.items():
        lines += [f"### `{target}`", "", *_metrics_table(results), "",
                  f"![Precision-recall](figures/{target}-pr-curves.png)",
                  f"![Calibration](figures/{target}-calibration.png)",
                  f"![Top features](figures/{target}-importance.png)", ""]
    lines += [
        "## Model",
        "",
        "LightGBM gradient boosting, early-stopped on the validation split by average precision,",
        "with isotonic calibration fitted on the validation split only. Explanations are SHAP",
        "contributions computed by LightGBM. Runs and the registered model are tracked in MLflow.",
        "",
        "## Limitations",
        "",
        "- Label noise: value additions recovered from text come from a keyword matcher with "
        "84% precision on a manual check of 50 cases; some additions with unusual wording are "
        "missed.",
        "- The size of each addition is not published by SECOP; the model predicts whether an "
        "addition happens, not how large it is.",
        "- `estado_contrato` is not kept up to date, so closure is inferred from end dates.",
        "- Colombia only; data lag of about two days behind the SECOP portal.",
        "- A high score reflects patterns of similar past contracts, not evidence about this one.",
        "",
        "## Ethical considerations",
        "",
        "- Natural-person suppliers are replaced by a salted hash before storage; their names "
        "and ID numbers never enter the dataset, figures or reports.",
        "- Public views aggregate by entity, region and contract type; there are no supplier "
        "rankings.",
        "- Outputs are framed as amendment risk signals and always shown with the disclaimer "
        "above.",
        "",
    ]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
