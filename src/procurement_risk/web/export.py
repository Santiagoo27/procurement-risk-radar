"""Privacy-safe static data for the web demo.

Writes, under `out_dir`:
    summary.json, departments.json, municipalities.json, entities.json,
    entities/<department-slug>.json   (each buyer's riskiest open contracts)

Observed rates use closed contracts signed in [observed_from, observed_to). The predicted
layer averages calibrated probabilities over open contracts signed in the two years
before `as_of` whose procurement process is available, scored with the serving bundle's
models and the training feature SQL.
No supplier fields or free text are ever written.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.build import feature_frame
from procurement_risk.features.history import build_history
from procurement_risk.features.labels import build_labels
from procurement_risk.model.explain import top_signals
from procurement_risk.serving.bundle import load_bundle
from procurement_risk.serving.labels import FEATURE_LABELS
from procurement_risk.serving.scoring import _percentile
from procurement_risk.web.geo import coverage, load_regions, match_regions

TARGETS = {"has_value_addition": "value_addition", "has_time_extension": "time_extension"}
TOP_CONTRACTS = 10
# Below this many scored open contracts the predicted layer is not representative.
MIN_OPEN_FOR_PREDICTED_LAYER = 10_000


def slugify(name: str | None) -> str:
    if not name:
        return "unknown"
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-") or "unknown"


def _unwrap_url(value) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value)
    if text.startswith("{"):
        try:
            text = ast.literal_eval(text).get("url", "")
        except (ValueError, SyntaxError):
            return None
    return text if text.startswith("https://") else None


def _clean(value):
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.date().isoformat()
    if value is pd.NA or value is None:
        return None
    return value


def _round_floats(node):
    if isinstance(node, float):
        return round(node, 4)
    if isinstance(node, dict):
        return {k: _round_floats(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_round_floats(v) for v in node]
    return node


def _write(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_round_floats(data), ensure_ascii=False, separators=(",", ":"),
                      default=_clean)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _aggregate(df: pd.DataFrame, key: str, min_n: int) -> pd.DataFrame:
    closed = df[df["observed"]].groupby(key).agg(
        n_closed=("contract_id", "size"),
        value_addition_rate=("has_value_addition", "mean"),
        extension_rate=("has_time_extension", "mean"))
    open_ = df[df["is_open"]].groupby(key).agg(
        n_open=("contract_id", "size"),
        predicted_value_addition=("p_value_addition", "mean"),
        predicted_extension=("p_time_extension", "mean"))
    agg = closed.join(open_, how="outer")
    agg[["n_closed", "n_open"]] = agg[["n_closed", "n_open"]].fillna(0).astype(int)
    small = agg["n_closed"] < min_n
    agg.loc[small, ["value_addition_rate", "extension_rate"]] = np.nan
    small_open = agg["n_open"] < min_n
    agg.loc[small_open, ["predicted_value_addition", "predicted_extension"]] = np.nan
    return agg


def _records(frame: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]


def export_web_data(raw_dirs: list[Path], bundle_dir: Path, topo_path: Path, out_dir: Path,
                    as_of: date, observed_from: date = date(2022, 1, 1),
                    observed_to: date = date(2025, 1, 1), min_n: int = 30) -> dict:
    bundle = load_bundle(bundle_dir)
    con = open_audit_db(raw_dirs)
    build_canonical(con)
    build_labels(con, as_of)
    rates = bundle.metadata["global_rates"]
    build_history(con, "buyer_id", "buyer", rates)
    build_history(con, "supplier_key", "supplier", rates)
    features = feature_frame(con, closed_only=False)
    extra = con.execute("""
        SELECT c.contract_id, c.buyer_city, l.is_closed, l.has_value_addition,
               l.has_time_extension, c.award_value,
               r.urlproceso, r.nombre_entidad
        FROM canonical_contracts c JOIN labels l USING (contract_id)
        JOIN contracts r ON r.id_contrato = c.contract_id
    """).df().drop_duplicates("contract_id")
    con.close()
    df = features.merge(extra, on="contract_id", how="left")

    signed = pd.to_datetime(df["signed_at"])
    df["observed"] = (df["is_closed"].astype(bool)
                      & (signed >= pd.Timestamp(observed_from))
                      & (signed < pd.Timestamp(observed_to)))
    # Only open contracts with their procurement process are scored: without it the award
    # value, budget and bidder features are missing and the estimate is unreliable.
    df["is_open"] = (~df["is_closed"].astype(bool)
                     & (signed >= pd.Timestamp(as_of - timedelta(days=730)))
                     & df["process_found"].astype(bool))
    for col in ("has_value_addition", "has_time_extension"):
        df[col] = df[col].astype(float)

    open_rows = df[df["is_open"]]
    for target, key in TARGETS.items():
        df[f"p_{key}"] = np.nan
        if len(open_rows):
            df.loc[open_rows.index, f"p_{key}"] = bundle.models[target].predict_proba(open_rows)

    regions = load_regions(topo_path)
    pairs = df[["buyer_department", "buyer_city"]].rename(
        columns={"buyer_department": "department", "buyer_city": "city"})
    matched = match_regions(pairs, regions)
    df["dpto_code"], df["mpio_code"] = matched["dpto_code"].values, matched["mpio_code"].values
    cov = coverage(matched[df["observed"].values], pd.Series(1, index=range(df["observed"].sum())))

    out_dir = Path(out_dir)
    if out_dir.exists():
        # Only ever replace a previous export, never an arbitrary directory.
        if any(out_dir.iterdir()) and not (out_dir / "summary.json").exists():
            raise ValueError(f"{out_dir} is not a web data directory (no summary.json); "
                             "refusing to delete it")
        shutil.rmtree(out_dir)
    sizes: dict[str, int] = {}
    observed = df[df["observed"]]

    names = regions.drop_duplicates("dpto_code").set_index("dpto_code")["dpto_name"]
    dpto = _aggregate(df, "dpto_code", min_n).reset_index().rename(columns={"dpto_code": "code"})
    dpto.insert(1, "name", dpto["code"].map(names))
    sizes["departments.json"] = _write(out_dir / "departments.json", _records(dpto))

    mnames = regions.set_index("mpio_code")
    mpio = _aggregate(df, "mpio_code", min_n).reset_index().rename(columns={"mpio_code": "code"})
    mpio.insert(1, "name", mpio["code"].map(mnames["mpio_name"]))
    mpio.insert(2, "dpto_code", mpio["code"].map(mnames["dpto_code"]))
    sizes["municipalities.json"] = _write(out_dir / "municipalities.json", _records(mpio))

    latest = (df.sort_values("signed_at")
              .groupby("buyer_id")[["nombre_entidad", "dpto_code", "mpio_code"]].last())
    ent = _aggregate(df, "buyer_id", min_n).join(latest).reset_index()
    ent = ent.rename(columns={"nombre_entidad": "name"})
    ent["dpto_slug"] = ent["dpto_code"].map(lambda c: slugify(names.get(c)) if c else "unknown")
    ent_cols = ["buyer_id", "name", "dpto_code", "mpio_code", "dpto_slug", "n_closed",
                "value_addition_rate", "extension_rate", "n_open", "predicted_value_addition",
                "predicted_extension"]
    sizes["entities.json"] = _write(out_dir / "entities.json", _records(ent[ent_cols]))

    # Contracts with no recorded value (comodatos, zero-value agreements) cannot receive a
    # meaningful "value addition", so they are scored for the aggregates but never listed.
    listable = open_rows[open_rows["award_value"].fillna(0) > 0]
    top = (listable.assign(p=df.loc[listable.index, "p_value_addition"])
           .sort_values("p", ascending=False).groupby("buyer_id").head(TOP_CONTRACTS))
    shards: dict[str, dict] = {}
    if len(top):
        signals = {t: top_signals(bundle.models[t], top, k=3) for t in TARGETS}
        quantiles = bundle.metadata["score_quantiles"]
        slug_of = ent.set_index("buyer_id")["dpto_slug"]
        for i, (_, row) in enumerate(top.iterrows()):
            # A natural-person supplier is named on the SECOP page, so those contracts are
            # listed without identifier or link (spec 5.4).
            flag = row["supplier_is_natural_person"]
            person = bool(pd.isna(flag) or flag)  # unknown counts as a person (fail-safe)
            item = {
                "id_contrato": None if person else row["contract_id"],
                "url": None if person else _unwrap_url(row["urlproceso"]),
                "supplier_is_natural_person": person,
                "signed_at": _clean(pd.Timestamp(row["signed_at"])),
                "contract_type": _clean(row["contract_type"]),
                "procurement_method": _clean(row["procurement_method"]),
                "award_value": _clean(row["award_value"]),
                "planned_duration_days": _clean(row["planned_duration_days"]),
            }
            for target, key in TARGETS.items():
                p = float(df.loc[row.name, f"p_{key}"])
                pct = _percentile(quantiles[target], p)
                item[key] = {"probability": p, "percentile": pct, "top_signals": [
                    {"feature": f, "label": FEATURE_LABELS[f] + (
                        "" if not pd.isna(row[f]) else " (not provided)"),
                     "provided": not pd.isna(row[f]), "contribution": round(v, 4)}
                    for f, v in signals[target][i]]}
            shard = shards.setdefault(slug_of.get(row["buyer_id"], "unknown"), {})
            shard.setdefault(row["buyer_id"], {"top_open": []})["top_open"].append(item)
    for slug, content in shards.items():
        sizes[f"entities/{slug}.json"] = _write(out_dir / "entities" / f"{slug}.json", content)

    summary = {
        "as_of": as_of.isoformat(),
        "observed_period": [observed_from.isoformat(), observed_to.isoformat()],
        "min_n": min_n,
        "n_closed": int(len(observed)),
        "n_open_scored": int(len(open_rows)),
        "predicted_layer_available": bool(len(open_rows) >= MIN_OPEN_FOR_PREDICTED_LAYER),
        "min_open_for_predicted_layer": MIN_OPEN_FOR_PREDICTED_LAYER,
        "national": {
            "value_addition_rate": _clean(observed["has_value_addition"].mean()),
            "extension_rate": _clean(observed["has_time_extension"].mean()),
            "predicted_value_addition": _clean(df["p_value_addition"].mean()),
            "predicted_extension": _clean(df["p_time_extension"].mean()),
        },
        "model_metrics": bundle.metadata["metrics"],
        "bundle_version": bundle.metadata["bundle_version"],
        "coverage": {k: v for k, v in cov.items() if k != "unmatched_top"},
    }
    sizes["summary.json"] = _write(out_dir / "summary.json", summary)
    return {"coverage": cov, "sizes": sizes, "n_closed": summary["n_closed"],
            "n_open_scored": summary["n_open_scored"]}
