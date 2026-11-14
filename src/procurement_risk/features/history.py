"""Point-in-time history features for buyers and suppliers.

For a contract signed at time t, only labels of other contracts that became observable
strictly before t are counted (observable_at = end date + grace, see labels.py). This is
done with cumulative sums per key ordered by observable_at and an ASOF join.
"""

from __future__ import annotations

import duckdb

_ALLOWED_KEYS = {"buyer_id", "supplier_key"}


def build_history(
    con: duckdb.DuckDBPyConnection,
    key: str,
    prefix: str,
    global_rates: dict[str, float],
    prior_strength: float = 20.0,
) -> None:
    if key not in _ALLOWED_KEYS or not prefix.isidentifier():
        raise ValueError(f"unsupported history key/prefix: {key!r}/{prefix!r}")
    g_add = float(global_rates["has_value_addition"])
    g_ext = float(global_rates["has_time_extension"])
    k = float(prior_strength)
    con.execute(f"""
        CREATE OR REPLACE TABLE history_{prefix} AS
        WITH events AS (
            SELECT c.{key} AS key, l.observable_at,
                   l.has_value_addition::INT AS add, l.has_time_extension::INT AS ext
            FROM canonical_contracts c JOIN labels l USING (contract_id)
            WHERE l.is_closed AND c.{key} IS NOT NULL AND l.observable_at IS NOT NULL
        ), cumulative AS (
            SELECT DISTINCT key, observable_at,
                   count(*) OVER w AS n, sum(add) OVER w AS n_add, sum(ext) OVER w AS n_ext
            FROM events
            WINDOW w AS (PARTITION BY key ORDER BY observable_at
                         RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        )
        SELECT c.contract_id,
               coalesce(h.n, 0) AS {prefix}_prior_n,
               (coalesce(h.n_add, 0) + {k} * {g_add}) / (coalesce(h.n, 0) + {k})
                   AS {prefix}_prior_value_addition_rate,
               (coalesce(h.n_ext, 0) + {k} * {g_ext}) / (coalesce(h.n, 0) + {k})
                   AS {prefix}_prior_extension_rate
        FROM canonical_contracts c
        ASOF LEFT JOIN cumulative h
            ON c.{key} = h.key AND c.signed_at > h.observable_at
    """)
