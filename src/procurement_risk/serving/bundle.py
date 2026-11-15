"""Serving bundle: calibrated models, buyer history as of the export date, and metadata.

Layout:
    <dir>/models/<target>.joblib
    <dir>/buyers.parquet      public entity fields + point-in-time history
    <dir>/metadata.json       version, as-of, features, global rates, metrics, quantiles

No supplier identifiers are ever written to a bundle.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from procurement_risk.config import DISCLAIMER
from procurement_risk.features.build import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGETS,
    _global_rates,
)
from procurement_risk.model.split import temporal_split
from procurement_risk.model.train import RiskModel

FEATURES = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]
BUYER_COLUMNS = (
    "buyer_id", "buyer_name", "buyer_department", "buyer_city", "buyer_order", "buyer_sector",
    "buyer_branch", "buyer_centralized", "buyer_prior_n", "buyer_prior_value_addition_rate",
    "buyer_prior_extension_rate",
)
PRIOR_STRENGTH = 20.0


CHECKED_LIBRARIES = ("lightgbm", "scikit-learn")


def library_versions() -> dict[str, str]:
    from importlib.metadata import version

    return {lib: version(lib) for lib in ("lightgbm", "scikit-learn", "numpy", "pandas")}


class BundleError(RuntimeError):
    """The bundle is incomplete or does not match this code version."""


@dataclass
class Bundle:
    models: dict[str, RiskModel]
    buyers: pd.DataFrame
    metadata: dict


def load_bundle(path: Path) -> Bundle:
    path = Path(path)
    meta_path = path / "metadata.json"
    if not meta_path.exists():
        raise BundleError(f"{meta_path} not found")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("features") != FEATURES:
        raise BundleError("bundle features do not match this code version's features")
    recorded = metadata.get("library_versions", {})
    current = library_versions()
    for lib in CHECKED_LIBRARIES:
        if recorded.get(lib) != current[lib]:
            raise BundleError(f"bundle was built with {lib} {recorded.get(lib)}, "
                              f"this environment has {current[lib]}")
    models = {}
    for target in TARGETS:
        model_path = path / "models" / f"{target}.joblib"
        if not model_path.exists():
            raise BundleError(f"missing model for {target}: {model_path}")
        models[target] = joblib.load(model_path)
    buyers = pd.read_parquet(path / "buyers.parquet")
    return Bundle(models=models, buyers=buyers, metadata=metadata)


def _quantiles(model: RiskModel, df: pd.DataFrame) -> list[float]:
    probs = model.predict_proba(df) if len(df) else np.zeros(1)
    return [float(q) for q in np.quantile(probs, np.linspace(0, 1, 101))]


def _write(out_dir: Path, models: dict[str, RiskModel], buyers: pd.DataFrame,
           metadata: dict) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "models").mkdir(parents=True)
    for target, model in models.items():
        joblib.dump(model, out_dir / "models" / f"{target}.joblib")
    buyers.loc[:, list(BUYER_COLUMNS)].to_parquet(out_dir / "buyers.parquet", index=False)
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return out_dir


def _metadata(version: str, as_of: str, global_rates: dict, metrics: dict,
              quantiles: dict, train_end: str = "2023-01-01",
              data_end: str = "2025-01-01") -> dict:
    return {
        "train_end": train_end,
        "data_end": data_end,
        "bundle_version": version,
        "as_of": as_of,
        "features": FEATURES,
        "categorical_features": list(CATEGORICAL_FEATURES),
        "global_rates": global_rates,
        "metrics": metrics,
        "score_quantiles": quantiles,
        "prior_strength": PRIOR_STRENGTH,
        "disclaimer": DISCLAIMER,
        "library_versions": library_versions(),
    }


def export_bundle(raw_dir: Path, dataset_path: Path, models_dir: Path, out_dir: Path,
                  as_of: date, split_dates: tuple[date, date, date] | None = None) -> Path:
    """`split_dates` = (train_end, valid_end, test_end) the models were trained with."""
    from procurement_risk.audit.metrics import open_audit_db
    from procurement_risk.canonical.colombia import build_canonical
    from procurement_risk.features.labels import build_labels

    con = open_audit_db(raw_dir)
    build_canonical(con)
    build_labels(con, as_of)
    rates = _global_rates(con)
    k, g_add, g_ext = PRIOR_STRENGTH, rates["has_value_addition"], rates["has_time_extension"]
    buyers = con.execute(f"""
        WITH latest AS (
            SELECT c.buyer_id, r.nombre_entidad AS buyer_name, c.buyer_department,
                   c.buyer_city, c.buyer_order, c.buyer_sector, c.buyer_branch,
                   c.buyer_centralized
            FROM canonical_contracts c JOIN contracts r ON r.id_contrato = c.contract_id
            WHERE c.buyer_id IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY c.buyer_id
                                       ORDER BY c.signed_at DESC NULLS LAST) = 1
        ), hist AS (
            SELECT c.buyer_id, count(*) AS n, sum(l.has_value_addition::INT) AS n_add,
                   sum(l.has_time_extension::INT) AS n_ext
            FROM canonical_contracts c JOIN labels l USING (contract_id)
            WHERE l.is_closed AND l.observable_at < TIMESTAMP '{as_of.isoformat()}'
              AND c.buyer_id IS NOT NULL
            GROUP BY c.buyer_id
        )
        SELECT latest.*, coalesce(h.n, 0) AS buyer_prior_n,
               (coalesce(h.n_add, 0) + {k} * {g_add}) / (coalesce(h.n, 0) + {k})
                   AS buyer_prior_value_addition_rate,
               (coalesce(h.n_ext, 0) + {k} * {g_ext}) / (coalesce(h.n, 0) + {k})
                   AS buyer_prior_extension_rate
        FROM latest LEFT JOIN hist h USING (buyer_id)
        ORDER BY buyer_id
    """).df()
    con.close()

    models = {t: joblib.load(Path(models_dir) / t / "model.joblib") for t in TARGETS}
    metrics = {t: json.loads((Path(models_dir) / t / "metrics.json").read_text(encoding="utf-8"))
               for t in TARGETS}
    dataset = pd.read_parquet(dataset_path)
    # Supplier/buyer smoothing must use the rates the model was trained with: closed
    # train-period rows of the training dataset, not labels rebuilt at the export date.
    splits = temporal_split(dataset, *split_dates) if split_dates else temporal_split(dataset)
    if len(splits.train):
        rates = {t: float(splits.train[t].astype(float).mean()) for t in TARGETS}
    test = splits.test
    reference = test if len(test) else dataset
    quantiles = {t: _quantiles(models[t], reference) for t in TARGETS}
    window = {}
    if split_dates:
        window = {"train_end": split_dates[0].isoformat(), "data_end": split_dates[2].isoformat()}
    meta = _metadata(as_of.isoformat(), as_of.isoformat(), rates, metrics, quantiles, **window)
    return _write(out_dir, models, buyers, meta)


DEMO_BUYERS = (("DEMO-A", "Demo Buyer A"), ("DEMO-B", "Demo Buyer B"),
               ("DEMO-C", "Alcaldía Demo C"))


def synthetic_dataset(n: int = 3000, seed: int = 0) -> pd.DataFrame:
    """Random dataset with the real schema; value addition driven by log_award_value."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "contract_id": [f"S{i}" for i in range(n)],
        "signed_at": pd.to_datetime("2021-01-01")
        + pd.to_timedelta(rng.integers(0, 4 * 365, n), unit="D"),
        "buyer_id": rng.choice([b for b, _ in DEMO_BUYERS], n),
    })
    for col in CATEGORICAL_FEATURES:
        df[col] = rng.choice(["a", "b", "c"], n)
    for col in NUMERIC_FEATURES:
        df[col] = rng.normal(size=n)
    logit = 2.5 * df["log_award_value"] - 2.0
    df["has_value_addition"] = rng.random(n) < 1 / (1 + np.exp(-logit))
    df["has_time_extension"] = rng.random(n) < 0.2
    return df


def make_demo_bundle(out_dir: Path, seed: int = 0) -> Path:
    """Tiny bundle trained on synthetic data, for tests and the CI Docker smoke test."""
    from procurement_risk.model.metrics import evaluate
    from procurement_risk.model.train import train_lightgbm

    df = synthetic_dataset(seed=seed)
    splits = temporal_split(df)
    models, metrics, quantiles = {}, {}, {}
    for target in TARGETS:
        model = train_lightgbm(splits, target, {"n_estimators": 100, "min_child_samples": 20})
        y = splits.test[target].astype(int)
        metrics[target] = {"lightgbm": evaluate(y, model.predict_raw(splits.test),
                                                y_prob=model.predict_proba(splits.test))}
        models[target] = model
        quantiles[target] = _quantiles(model, splits.test)
    buyers = pd.DataFrame([{
        "buyer_id": bid, "buyer_name": name, "buyer_department": "a", "buyer_city": "Demo City",
        "buyer_order": "a", "buyer_sector": "a", "buyer_branch": "a", "buyer_centralized": "a",
        "buyer_prior_n": 10 * (i + 1), "buyer_prior_value_addition_rate": 0.05 * (i + 1),
        "buyer_prior_extension_rate": 0.1,
    } for i, (bid, name) in enumerate(DEMO_BUYERS)])
    rates = {t: float(df[t].mean()) for t in TARGETS}
    meta = _metadata("demo", "2026-11-14", rates, metrics, quantiles)
    return _write(out_dir, models, buyers, meta)
