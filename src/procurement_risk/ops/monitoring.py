"""Weekly model monitoring: feature drift (PSI), score shift and realized performance.

- Reference window: contracts signed before the production model's training cut-off.
- Current window: contracts signed in the last 90 days.
- Realized performance: contracts that have closed and were signed after the model's
  training data ended (out-of-time), scored with the production bundle.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from procurement_risk.model.metrics import evaluate
from procurement_risk.serving.bundle import Bundle
from procurement_risk.serving.labels import FEATURE_LABELS

EPS = 1e-4
MAX_REFERENCE_ROWS = 200_000


def psi(reference: pd.Series, current: pd.Series, bins: int = 10,
        min_rows: int | None = None) -> float | None:
    """Population stability index; None when either side has too few non-null values."""
    from procurement_risk.ops import config

    min_rows = config.MONITORING.min_rows if min_rows is None else min_rows
    ref, cur = reference.dropna(), current.dropna()
    if len(ref) < min_rows or len(cur) < min_rows:
        return None
    if pd.api.types.is_numeric_dtype(ref) and pd.api.types.is_numeric_dtype(cur):
        edges = np.unique(np.quantile(ref.astype(float), np.linspace(0, 1, bins + 1)))
        if len(edges) < 2:
            return 0.0
        edges[0], edges[-1] = -np.inf, np.inf
        r = np.histogram(ref.astype(float), edges)[0] / len(ref)
        c = np.histogram(cur.astype(float), edges)[0] / len(cur)
    else:
        cats = pd.Index(ref.astype(str).unique()).union(cur.astype(str).unique())
        r = ref.astype(str).value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy()
        c = cur.astype(str).value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy()
    r, c = np.clip(r, EPS, None), np.clip(c, EPS, None)
    return float(np.sum((c - r) * np.log(c / r)))


def _round(x: float | None, digits: int = 4) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), digits)


def build_report(frame: pd.DataFrame, bundle: Bundle, as_of: date, reference_end: date,
                 data_end: date) -> dict:
    """`frame`: features + `signed_at`, `is_closed` and both targets for every contract."""
    from procurement_risk.ops import config

    t = config.MONITORING
    signed = pd.to_datetime(frame["signed_at"])
    cur_start = as_of - timedelta(days=t.current_window_days)
    reference = frame[signed < pd.Timestamp(reference_end)]
    if len(reference) > MAX_REFERENCE_ROWS:
        reference = reference.sample(MAX_REFERENCE_ROWS, random_state=0)
    current = frame[(signed >= pd.Timestamp(cur_start)) & (signed <= pd.Timestamp(as_of))]

    drift = []
    for feature in (*CATEGORICAL_FEATURES, *NUMERIC_FEATURES):
        value = psi(reference[feature], current[feature])
        expected = feature in config.EXPECTED_DRIFT
        drift.append({"feature": feature, "label": FEATURE_LABELS[feature],
                      "psi": _round(value), "expected": expected,
                      "shifted": bool(not expected and value is not None
                                      and value > t.psi_shifted)})
    drift.sort(key=lambda d: (not d["expected"], -1 if d["psi"] is None else d["psi"]),
               reverse=True)

    model = bundle.models["has_value_addition"]
    score_shift = {"reference_mean": None, "current_mean": None}
    if len(reference) and len(current) >= t.min_rows:
        ref_p, cur_p = model.predict_proba(reference), model.predict_proba(current)
        score_shift = {"reference_mean": _round(ref_p.mean()), "current_mean": _round(cur_p.mean()),
                       "reference_p90": _round(np.quantile(ref_p, 0.9)),
                       "current_p90": _round(np.quantile(cur_p, 0.9))}

    test_pr = bundle.metadata.get("metrics", {}).get("has_value_addition", {}) \
        .get("lightgbm", {}).get("pr_auc")
    # Only contracts whose tender data was found: the others are scored without award value
    # or bidders, which would measure the data gap rather than the model.
    complete = frame["process_found"].astype(bool) if "process_found" in frame else True
    out_of_time = frame[frame["is_closed"].astype(bool) & (signed >= pd.Timestamp(data_end))
                        & complete]
    labels = out_of_time["has_value_addition"].dropna().astype(int) if len(out_of_time) else []
    if len(out_of_time) < t.min_rows or len(set(labels)) < 2:
        realized = {"pr_auc": None, "n": int(len(out_of_time)), "test_pr_auc": test_pr,
                    "reason": f"fewer than {t.min_rows} closed contracts signed after "
                              f"{data_end.isoformat()} yet"}
    else:
        m = evaluate(labels.to_numpy(), model.predict_raw(out_of_time),
                     y_prob=model.predict_proba(out_of_time))
        realized = {"pr_auc": _round(m["pr_auc"]), "positive_rate": _round(m["positive_rate"]),
                    "n": int(len(out_of_time)), "test_pr_auc": test_pr, "reason": None}

    computable = [d for d in drift if d["psi"] is not None and not d["expected"]]
    if not computable:
        status = "insufficient_data"
    elif any(d["shifted"] for d in computable) or (
            realized["pr_auc"] is not None and test_pr is not None
            and realized["pr_auc"] < test_pr - t.realized_pr_auc_drop):
        status = "watch"
    else:
        status = "ok"

    return {
        "as_of": as_of.isoformat(),
        "status": status,
        "windows": {"reference": [None, reference_end.isoformat()],
                    "current": [cur_start.isoformat(), as_of.isoformat()]},
        "n_reference": int(len(reference)),
        "n_current": int(len(current)),
        "feature_drift": drift,
        "score_shift": score_shift,
        "realized": realized,
    }


def monitor_from_raw(raw_dirs: list[Path], bundle_dir: Path, as_of: date) -> dict:
    """Rebuild features for every contract from raw data and build the report."""
    from procurement_risk.audit.metrics import open_audit_db
    from procurement_risk.canonical.colombia import build_canonical
    from procurement_risk.features.build import feature_frame
    from procurement_risk.features.history import build_history
    from procurement_risk.features.labels import build_labels
    from procurement_risk.serving.bundle import load_bundle

    bundle = load_bundle(bundle_dir)
    con = open_audit_db(raw_dirs)
    build_canonical(con)
    build_labels(con, as_of)
    rates = bundle.metadata["global_rates"]
    build_history(con, "buyer_id", "buyer", rates)
    build_history(con, "supplier_key", "supplier", rates)
    features = feature_frame(con, closed_only=False)
    labels = con.execute("SELECT contract_id, is_closed, has_value_addition, has_time_extension "
                         "FROM labels").df()
    con.close()
    frame = features.merge(labels, on="contract_id", how="left")
    reference_end = date.fromisoformat(bundle.metadata.get("train_end", "2023-01-01"))
    data_end = date.fromisoformat(bundle.metadata.get("data_end", "2025-01-01"))
    return build_report(frame, bundle, as_of, reference_end, data_end)
