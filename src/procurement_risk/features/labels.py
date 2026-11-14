"""Targets and the closure rule (docs/data-audit.md).

- has_value_addition: an explicit 'Adicion en el valor' amendment, or a generic amendment
  whose text describes a value addition.
- has_time_extension: dias_adicionados > 0, or an 'Extension' amendment.
- A contract is closed when its current end date is at least `grace_days` before `as_of`;
  only closed contracts get labels. estado_contrato is never used (it is stale).
- observable_at = end date + grace: the moment a contract's label can be trusted. History
  features may only use labels observable before a contract's signing date.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb


def build_labels(con: duckdb.DuckDBPyConnection, as_of: date, grace_days: int = 180) -> None:
    cutoff = as_of - timedelta(days=grace_days)
    con.execute(f"""
        CREATE OR REPLACE TABLE labels AS
        WITH a AS (
            SELECT contract_id,
                   bool_or(kind IN ('value_addition', 'value_addition_text')) AS any_addition,
                   bool_or(kind = 'extension') AS any_extension
            FROM canonical_amendments GROUP BY contract_id
        ), base AS (
            SELECT c.contract_id,
                   coalesce(c.current_end_at <= TIMESTAMP '{cutoff.isoformat()}', false)
                       AS is_closed,
                   coalesce(a.any_addition, false) AS addition,
                   coalesce(c.added_days, 0) > 0 OR coalesce(a.any_extension, false)
                       AS extension,
                   c.current_end_at + INTERVAL {grace_days} DAY AS observable_at
            FROM canonical_contracts c LEFT JOIN a USING (contract_id)
        )
        SELECT contract_id, is_closed,
               CASE WHEN is_closed THEN addition END AS has_value_addition,
               CASE WHEN is_closed THEN extension END AS has_time_extension,
               observable_at
        FROM base
    """)
