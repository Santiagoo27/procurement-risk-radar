"""How big are value additions? Measured from the nightly snapshot archive.

SECOP does not publish the amount of each addition, but the archive records each contract's
current value over time. An addition shows up as an increase between the first value the
archive saw and the latest one. Decreases (corrections, reductions) are not additions.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_history(snapshot_dir: Path) -> pd.DataFrame:
    files = sorted(Path(snapshot_dir).glob("baseline-*.parquet")) + \
        sorted(Path(snapshot_dir).glob("changes-*.parquet"))
    if not files:
        return pd.DataFrame(columns=["id_contrato", "valor_del_contrato",
                                     "ultima_actualizacion", "snapshot_date"])
    cols = ["id_contrato", "valor_del_contrato", "ultima_actualizacion", "snapshot_date"]
    return pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)


def value_changes(history: pd.DataFrame) -> pd.DataFrame:
    """Contracts whose value increased since the archive first saw them."""
    if history.empty:
        return pd.DataFrame(columns=["id_contrato", "first_value", "latest_value",
                                     "increase_pct"])
    ordered = history.sort_values(["snapshot_date", "ultima_actualizacion"], kind="stable")
    grouped = ordered.groupby("id_contrato")["valor_del_contrato"]
    out = pd.DataFrame({"first_value": grouped.first(), "latest_value": grouped.last()})
    out = out[(out["first_value"] > 0) & (out["latest_value"] > out["first_value"])]
    out["increase_pct"] = out["latest_value"] / out["first_value"] - 1
    return out.reset_index()


def summary(history: pd.DataFrame, min_n: int | None = None) -> dict:
    from procurement_risk.ops import config

    min_n = config.SEVERITY_MIN_N if min_n is None else min_n
    changes = value_changes(history)
    since = None
    if not history.empty:
        since = pd.to_datetime(history["snapshot_date"]).min().date().isoformat()
    result = {
        "since": since,
        "n_contracts_observed": int(history["id_contrato"].nunique()) if len(history) else 0,
        "n_increased": int(len(changes)),
        "median_increase_pct": None, "p75_increase_pct": None, "p90_increase_pct": None,
        "share_over_30pct": None,
        "reason": None,
    }
    if len(changes) < min_n:
        result["reason"] = (f"fewer than {min_n} contracts have increased in value since "
                            "the archive started")
        return result
    pct = changes["increase_pct"].to_numpy()
    result.update({
        "median_increase_pct": round(float(np.median(pct)), 4),
        "p75_increase_pct": round(float(np.quantile(pct, 0.75)), 4),
        "p90_increase_pct": round(float(np.quantile(pct, 0.9)), 4),
        "share_over_30pct": round(float((pct > 0.3).mean()), 4),
    })
    return result
