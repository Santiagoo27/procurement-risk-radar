"""How big are value additions? Measured from the nightly snapshot archive.

SECOP does not publish the amount of each addition, but the archive records each contract's
current value over time. An addition shows up as an increase between the first value the
archive saw and the latest one. Decreases (corrections, reductions) are not additions.

Only the earliest baseline plus every changes file is read: later monthly baselines repeat
values already known, and new contracts appear in the changes files when they are published.
The aggregation runs in DuckDB so memory stays flat as the archive grows.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def archive_files(snapshot_dir: Path) -> list[Path]:
    """The earliest baseline plus all changes files, in name (date) order."""
    snapshot_dir = Path(snapshot_dir)
    baselines = sorted(snapshot_dir.glob("baseline-*.parquet"))
    return baselines[:1] + sorted(snapshot_dir.glob("changes-*.parquet"))


def _query(snapshot_dir: Path, sql: str) -> pd.DataFrame | None:
    files = archive_files(snapshot_dir)
    if not files:
        return None
    paths = ", ".join(f"'{p.as_posix()}'" for p in files)
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW history AS SELECT id_contrato, valor_del_contrato, ultima_actualizacion,
               snapshot_date
        FROM read_parquet([{paths}], union_by_name = true)
    """)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


_CHANGES_SQL = """
    WITH per_contract AS (
        SELECT id_contrato,
               first(valor_del_contrato ORDER BY snapshot_date, ultima_actualizacion)
                   AS first_value,
               last(valor_del_contrato ORDER BY snapshot_date, ultima_actualizacion)
                   AS latest_value
        FROM history GROUP BY id_contrato
    )
    SELECT id_contrato, first_value, latest_value, latest_value / first_value - 1 AS increase_pct
    FROM per_contract
    WHERE first_value > 0 AND latest_value > first_value
"""


def value_changes(snapshot_dir: Path) -> pd.DataFrame:
    """Contracts whose value increased since the archive first saw them."""
    out = _query(snapshot_dir, _CHANGES_SQL)
    if out is None:
        return pd.DataFrame(columns=["id_contrato", "first_value", "latest_value",
                                     "increase_pct"])
    return out


def summary(snapshot_dir: Path, min_n: int | None = None) -> dict:
    from procurement_risk.ops import config

    min_n = config.SEVERITY_MIN_N if min_n is None else min_n
    result = {
        "since": None, "n_contracts_observed": 0, "n_increased": 0,
        "median_increase_pct": None, "p75_increase_pct": None, "p90_increase_pct": None,
        "share_over_30pct": None, "reason": None,
    }
    stats = _query(snapshot_dir, f"""
        WITH c AS ({_CHANGES_SQL})
        SELECT (SELECT min(snapshot_date) FROM history) AS since,
               (SELECT count(DISTINCT id_contrato) FROM history) AS observed,
               count(*) AS increased,
               median(increase_pct) AS p50,
               quantile_cont(increase_pct, 0.75) AS p75,
               quantile_cont(increase_pct, 0.9) AS p90,
               avg((increase_pct > 0.3)::DOUBLE) AS over30
        FROM c
    """)
    if stats is None:
        result["reason"] = "the snapshot archive is empty"
        return result
    row = stats.iloc[0]
    result.update({
        "since": pd.Timestamp(row["since"]).date().isoformat(),
        "n_contracts_observed": int(row["observed"]),
        "n_increased": int(row["increased"]),
    })
    if result["n_increased"] < min_n:
        result["reason"] = (f"fewer than {min_n} contracts have increased in value since "
                            "the archive started")
        return result
    result.update({
        "median_increase_pct": round(float(row["p50"]), 4),
        "p75_increase_pct": round(float(row["p75"]), 4),
        "p90_increase_pct": round(float(row["p90"]), 4),
        "share_over_30pct": round(float(row["over30"]), 4),
    })
    return result
