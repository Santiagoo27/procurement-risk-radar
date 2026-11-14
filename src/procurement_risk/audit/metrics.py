"""DuckDB queries that answer the Phase 0 data-audit questions (spec section 12)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from procurement_risk.audit.text import looks_like_value_addition

VALUE_ADDITION = "Adicion en el valor"
HIDDEN_TYPES = ("Modificacion General", "No definido")


def open_audit_db(raw_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name in ("contracts", "amendments", "processes"):
        pattern = (Path(raw_dir) / name / "*.parquet").as_posix()
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{pattern}')")
    con.create_function(
        "looks_like_value_addition", looks_like_value_addition, ["VARCHAR"], "BOOLEAN",
        null_handling="special",
    )
    con.execute(f"""
        CREATE TEMP TABLE value_added AS
        SELECT DISTINCT id_contrato FROM amendments
        WHERE tipo = '{VALUE_ADDITION}' AND id_contrato IS NOT NULL
    """)
    # One process row per portfolio id: the one with the largest awarded value.
    con.execute("""
        CREATE TEMP TABLE process_one AS
        SELECT * FROM processes
        QUALIFY row_number() OVER (
            PARTITION BY id_del_portafolio ORDER BY valor_total_adjudicacion DESC NULLS LAST
        ) = 1
    """)
    return con


def _dicts(con: duckdb.DuckDBPyConnection, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def label_rates_by_year(con: duckdb.DuckDBPyConnection) -> list[dict]:
    return _dicts(con, """
        SELECT year(c.fecha_de_firma) AS year,
               count(*) AS n_contracts,
               avg(CASE WHEN v.id_contrato IS NOT NULL THEN 1 ELSE 0 END) AS value_addition_rate,
               avg(CASE WHEN coalesce(c.dias_adicionados, 0) > 0 THEN 1 ELSE 0 END)
                   AS extension_rate
        FROM contracts c LEFT JOIN value_added v USING (id_contrato)
        GROUP BY 1 ORDER BY 1
    """)


def hidden_value_additions(con: duckdb.DuckDBPyConnection, sample_size: int = 50) -> dict:
    in_sample = "id_contrato IN (SELECT id_contrato FROM contracts)"
    explicit = con.execute(
        f"SELECT count(*) FROM amendments WHERE tipo = '{VALUE_ADDITION}' AND {in_sample}"
    ).fetchone()[0]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE hidden AS
        SELECT identificador, id_contrato, descripcion FROM amendments
        WHERE tipo IN {HIDDEN_TYPES} AND {in_sample}
          AND (descripcion ILIKE '%adic%' OR descripcion ILIKE '%mayor valor%')
          AND looks_like_value_addition(descripcion)
    """)
    hidden = con.execute("SELECT count(*) FROM hidden").fetchone()[0]
    sample = [r[0] for r in con.execute(
        "SELECT descripcion FROM hidden ORDER BY md5(identificador) LIMIT ?", [sample_size]
    ).fetchall()]
    total = explicit + hidden
    return {
        "explicit": explicit,
        "hidden_matches": hidden,
        "hidden_share": hidden / total if total else 0.0,
        "hidden_contracts": con.execute(
            "SELECT count(DISTINCT id_contrato) FROM hidden h WHERE NOT EXISTS "
            "(SELECT 1 FROM value_added v WHERE v.id_contrato = h.id_contrato)"
        ).fetchone()[0],
        "sample": sample,
    }


def value_vs_award(con: duckdb.DuckDBPyConnection) -> dict:
    row = _dicts(con, """
        WITH j AS (
            SELECT c.id_contrato, c.valor_del_contrato, p.valor_total_adjudicacion,
                   p.id_del_portafolio IS NOT NULL AS joined,
                   v.id_contrato IS NOT NULL AS has_addition
            FROM contracts c
            LEFT JOIN process_one p ON c.proceso_de_compra = p.id_del_portafolio
            LEFT JOIN value_added v ON c.id_contrato = v.id_contrato
        ), r AS (
            SELECT has_addition, valor_del_contrato / valor_total_adjudicacion AS ratio
            FROM j WHERE joined AND valor_total_adjudicacion > 0 AND valor_del_contrato > 0
        )
        SELECT (SELECT avg(joined::INT) FROM j) AS join_rate,
               (SELECT median(ratio) FROM r WHERE has_addition) AS median_ratio_with_addition,
               (SELECT median(ratio) FROM r WHERE NOT has_addition)
                   AS median_ratio_without_addition,
               (SELECT count(*) FROM r WHERE has_addition) AS n_with_addition,
               (SELECT count(*) FROM r WHERE NOT has_addition) AS n_without_addition
    """)[0]
    return row


_DURATION_DAYS = """
    CASE
        WHEN regexp_matches(lower(duraci_n_del_contrato), '^\\s*\\d+(\\.\\d+)?\\s*d[ií]a')
            THEN 1
        WHEN regexp_matches(lower(duraci_n_del_contrato), '^\\s*\\d+(\\.\\d+)?\\s*semana')
            THEN 7
        WHEN regexp_matches(lower(duraci_n_del_contrato), '^\\s*\\d+(\\.\\d+)?\\s*mes')
            THEN 30
        WHEN regexp_matches(lower(duraci_n_del_contrato), '^\\s*\\d+(\\.\\d+)?\\s*a[ñn]o')
            THEN 365
    END * TRY_CAST(regexp_extract(duraci_n_del_contrato, '^\\s*(\\d+(\\.\\d+)?)', 1) AS DOUBLE)
"""


def end_date_vs_duration(con: duckdb.DuckDBPyConnection) -> dict:
    return _dicts(con, f"""
        WITH e AS (
            SELECT {_DURATION_DAYS} AS original_days,
                   date_diff('day', fecha_de_inicio_del_contrato, fecha_de_fin_del_contrato)
                       AS span_days,
                   dias_adicionados
            FROM contracts WHERE dias_adicionados > 0
        )
        SELECT count(*) AS n,
               avg(CASE WHEN span_days - original_days >= 0.8 * dias_adicionados THEN 1.0
                        ELSE 0.0 END) FILTER (WHERE original_days IS NOT NULL
                                              AND span_days IS NOT NULL)
                   AS share_end_date_moved,
               avg(CASE WHEN original_days IS NULL THEN 1.0 ELSE 0.0 END)
                   AS share_duration_unparseable
        FROM e
    """)[0]


def closure_states(con: duckdb.DuckDBPyConnection, as_of: date) -> list[dict]:
    cutoff = as_of - timedelta(days=180)
    return _dicts(con, """
        SELECT estado_contrato, count(*) AS n,
               avg(CASE WHEN fecha_de_fin_del_contrato < ? THEN 1.0 ELSE 0.0 END)
                   AS share_end_before_as_of_minus_180d
        FROM contracts GROUP BY 1 ORDER BY n DESC
    """, [cutoff])


def bidder_coverage(con: duckdb.DuckDBPyConnection) -> dict:
    return _dicts(con, """
        WITH j AS (
            SELECT p.id_del_portafolio IS NOT NULL AS joined,
                   p.proveedores_unicos_con, p.respuestas_al_procedimiento
            FROM contracts c
            LEFT JOIN process_one p ON c.proceso_de_compra = p.id_del_portafolio
        )
        SELECT avg(joined::INT) AS join_rate,
               avg((proveedores_unicos_con IS NOT NULL)::INT) FILTER (WHERE joined)
                   AS unique_bidders_coverage,
               avg((respuestas_al_procedimiento IS NOT NULL)::INT) FILTER (WHERE joined)
                   AS responses_coverage,
               avg((proveedores_unicos_con = 1)::INT)
                   FILTER (WHERE joined AND proveedores_unicos_con IS NOT NULL)
                   AS single_bidder_share
        FROM j
    """)[0]
