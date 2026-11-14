"""Targets, the closure rule and when each label becomes observable.

- has_value_addition: an explicit 'Adicion en el valor' amendment, or a generic amendment
  whose text describes a value addition (docs/data-audit.md).
- has_time_extension: dias_adicionados > 0, or an 'Extension' amendment.
- Closure uses the *planned* end date (planned start, or signing date, + planned duration),
  falling back to the current end date when no planned duration is known. The current end
  date is moved by extensions, so closing on it would drop extended contracts from recent
  periods and bias labels. estado_contrato is never used (it is stale).
- observable_at: when a contract's label can be trusted by history features. It is the
  latest of (current end, planned end, signing date) + grace, and never earlier than the
  last label-bearing amendment. Anchoring on the signing date stops bad end dates from
  leaking a contract's label into its own (or earlier contracts') history.
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
                   bool_or(kind = 'extension') AS any_extension,
                   max(recorded_at) FILTER (WHERE kind <> 'other') AS last_label_amendment_at
            FROM canonical_amendments GROUP BY contract_id
        ), planned AS (
            SELECT c.*,
                   CASE WHEN c.planned_duration_days IS NOT NULL
                        THEN coalesce(c.planned_start_at, c.signed_at)
                             + to_days(CAST(round(c.planned_duration_days) AS INTEGER))
                   END AS planned_end_at
            FROM canonical_contracts c
        ), base AS (
            SELECT p.contract_id,
                   coalesce(coalesce(p.planned_end_at, p.current_end_at)
                            <= TIMESTAMP '{cutoff.isoformat()}', false) AS is_closed,
                   coalesce(a.any_addition, false) AS addition,
                   coalesce(p.added_days, 0) > 0 OR coalesce(a.any_extension, false)
                       AS extension,
                   CASE WHEN p.signed_at IS NOT NULL THEN greatest(
                       greatest(p.current_end_at, p.planned_end_at, p.signed_at)
                           + INTERVAL {grace_days} DAY,
                       a.last_label_amendment_at
                   ) END AS observable_at
            FROM planned p LEFT JOIN a USING (contract_id)
        )
        SELECT contract_id, is_closed,
               CASE WHEN is_closed THEN addition END AS has_value_addition,
               CASE WHEN is_closed THEN extension END AS has_time_extension,
               observable_at
        FROM base
    """)
