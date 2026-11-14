"""Score contract requests with the training feature SQL (no train/serve skew).

A request carries signing-time attributes plus a buyer_id. Buyer attributes and history
come from the bundle; supplier history is not served (no supplier identifiers), so every
request uses supplier_prior_n = 0 and the training-period global rates.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from procurement_risk.canonical.colombia import MAX_DURATION_DAYS, SEGMENT_SQL
from procurement_risk.features.build import CATEGORICAL_FEATURES, feature_frame
from procurement_risk.model.explain import top_signals
from procurement_risk.serving.bundle import Bundle
from procurement_risk.serving.labels import FEATURE_LABELS

TARGET_KEYS = {"has_value_addition": "value_addition", "has_time_extension": "time_extension"}
REQUEST_FIELDS = (
    "buyer_id", "signed_at", "planned_start_at", "procurement_method", "contract_type",
    "category_code", "funding_source", "award_value", "tender_budget", "planned_duration_days",
    "tender_published_at", "n_bidders", "n_responses", "n_invited", "n_lots",
    "supplier_is_natural_person", "supplier_is_sme", "supplier_is_group",
    "advance_payment_enabled", "extendable_clause",
)
BUYER_ATTRIBUTES = ("buyer_department", "buyer_order", "buyer_sector", "buyer_branch",
                    "buyer_centralized")


class UnknownBuyerError(KeyError):
    """The request's buyer_id is not in the bundle."""


def _requests_frame(bundle: Bundle, contracts: list[dict[str, Any]]) -> pd.DataFrame:
    buyers = bundle.buyers.set_index("buyer_id")
    rows = []
    for i, contract in enumerate(contracts):
        buyer_id = contract.get("buyer_id")
        if buyer_id not in buyers.index:
            raise UnknownBuyerError(buyer_id)
        row = {f: contract.get(f) for f in REQUEST_FIELDS}
        row["contract_id"] = f"r{i:05d}"
        row["signed_at"] = row["signed_at"] or date.today()
        buyer = buyers.loc[buyer_id]
        for col in (*BUYER_ATTRIBUTES, "buyer_prior_n", "buyer_prior_value_addition_rate",
                    "buyer_prior_extension_rate"):
            row[col] = buyer[col]
        rows.append(row)
    return pd.DataFrame(rows).astype(object).where(lambda d: d.notna(), None)


def features_for(bundle: Bundle, contracts: list[dict[str, Any]]) -> pd.DataFrame:
    """Model features for each request, in request order."""
    req = _requests_frame(bundle, contracts)
    rates = bundle.metadata["global_rates"]
    con = duckdb.connect()
    con.register("req", req)
    segment = SEGMENT_SQL.format(col="CAST(category_code AS VARCHAR)")
    con.execute(f"""
        CREATE TABLE canonical_contracts AS SELECT
            CAST(contract_id AS VARCHAR) AS contract_id,
            CAST(buyer_id AS VARCHAR) AS buyer_id,
            CAST(buyer_department AS VARCHAR) AS buyer_department,
            CAST(buyer_order AS VARCHAR) AS buyer_order,
            CAST(buyer_sector AS VARCHAR) AS buyer_sector,
            CAST(buyer_branch AS VARCHAR) AS buyer_branch,
            CAST(buyer_centralized AS VARCHAR) AS buyer_centralized,
            CAST(procurement_method AS VARCHAR) AS procurement_method,
            CAST(contract_type AS VARCHAR) AS contract_type,
            {segment} AS category_segment,
            CAST(funding_source AS VARCHAR) AS funding_source,
            CAST(signed_at AS TIMESTAMP) AS signed_at,
            CAST(planned_start_at AS TIMESTAMP) AS planned_start_at,
            coalesce(TRY_CAST(award_value AS DOUBLE), TRY_CAST(tender_budget AS DOUBLE))
                AS award_value,
            TRY_CAST(tender_budget AS DOUBLE) AS tender_budget,
            CASE WHEN TRY_CAST(planned_duration_days AS DOUBLE) > 0
                  AND TRY_CAST(planned_duration_days AS DOUBLE) <= {MAX_DURATION_DAYS}
                 THEN TRY_CAST(planned_duration_days AS DOUBLE) END AS planned_duration_days,
            CAST(tender_published_at AS TIMESTAMP) AS tender_published_at,
            TRY_CAST(n_bidders AS BIGINT) AS n_bidders,
            TRY_CAST(n_responses AS BIGINT) AS n_responses,
            TRY_CAST(n_invited AS BIGINT) AS n_invited,
            TRY_CAST(n_lots AS BIGINT) AS n_lots,
            TRY_CAST(supplier_is_natural_person AS BOOLEAN) AS supplier_is_natural_person,
            TRY_CAST(supplier_is_sme AS BOOLEAN) AS supplier_is_sme,
            TRY_CAST(supplier_is_group AS BOOLEAN) AS supplier_is_group,
            TRY_CAST(advance_payment_enabled AS BOOLEAN) AS advance_payment_enabled,
            TRY_CAST(extendable_clause AS BOOLEAN) AS extendable_clause,
            TRUE AS process_found
        FROM req
    """)
    con.execute("""
        CREATE TABLE history_buyer AS SELECT CAST(contract_id AS VARCHAR) AS contract_id,
            CAST(buyer_prior_n AS BIGINT) AS buyer_prior_n,
            CAST(buyer_prior_value_addition_rate AS DOUBLE) AS buyer_prior_value_addition_rate,
            CAST(buyer_prior_extension_rate AS DOUBLE) AS buyer_prior_extension_rate
        FROM req
    """)
    con.execute(f"""
        CREATE TABLE history_supplier AS SELECT CAST(contract_id AS VARCHAR) AS contract_id,
            0::BIGINT AS supplier_prior_n,
            {float(rates["has_value_addition"])}::DOUBLE AS supplier_prior_value_addition_rate,
            {float(rates["has_time_extension"])}::DOUBLE AS supplier_prior_extension_rate
        FROM req
    """)
    features = feature_frame(con, closed_only=False)
    con.close()
    return features.sort_values("contract_id").reset_index(drop=True)


def _percentile(quantiles: list[float], p: float) -> float:
    return float(np.clip(np.searchsorted(np.asarray(quantiles), p, side="right") - 1, 0, 100))


def score(bundle: Bundle, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = features_for(bundle, contracts)
    any_model = next(iter(bundle.models.values()))
    warnings: list[list[str]] = [[] for _ in range(len(features))]
    for col in CATEGORICAL_FEATURES:
        known = set(any_model.categories[col])
        for i, value in enumerate(features[col]):
            if value is not None and not pd.isna(value) and value not in known:
                warnings[i].append(f"unseen value for {col}: {value}")

    results: list[dict[str, Any]] = [{"warnings": w} for w in warnings]
    for target, key in TARGET_KEYS.items():
        model = bundle.models[target]
        probs = model.predict_proba(features)
        signals = top_signals(model, features, k=3)
        quantiles = bundle.metadata["score_quantiles"][target]
        for i, result in enumerate(results):
            result[key] = {
                "probability": float(probs[i]),
                "percentile": _percentile(quantiles, float(probs[i])),
                "top_signals": [{"feature": name, "label": FEATURE_LABELS[name],
                                 "contribution": round(value, 4)}
                                for name, value in signals[i]],
            }
    return results
