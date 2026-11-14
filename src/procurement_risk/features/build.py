"""Assemble the leakage-safe training dataset (closed contracts only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.history import build_history
from procurement_risk.features.labels import build_labels

TRAIN_END = date(2023, 1, 1)

CATEGORICAL_FEATURES: tuple[str, ...] = (
    "buyer_department", "buyer_order", "buyer_sector", "buyer_branch", "buyer_centralized",
    "procurement_method", "contract_type", "category_segment", "funding_source",
)
NUMERIC_FEATURES: tuple[str, ...] = (
    "log_award_value", "log_tender_budget", "award_to_budget_ratio", "planned_duration_days",
    "days_publication_to_signing", "days_signing_to_start", "n_bidders", "single_bidder",
    "n_responses", "n_invited", "n_lots", "signing_month", "signed_in_december",
    "supplier_is_natural_person", "supplier_is_sme", "supplier_is_group",
    "advance_payment_enabled", "extendable_clause",
    "buyer_prior_n", "buyer_prior_value_addition_rate", "buyer_prior_extension_rate",
    "supplier_prior_n", "supplier_prior_value_addition_rate", "supplier_prior_extension_rate",
)
TARGETS: tuple[str, ...] = ("has_value_addition", "has_time_extension")


@dataclass
class DatasetSummary:
    n_rows: int
    n_without_process: int
    positive_rate: dict[str, float] = field(default_factory=dict)


def _global_rates(con) -> dict[str, float]:
    """Label rates of closed train-period contracts (prior for history smoothing)."""
    row = con.execute(f"""
        SELECT avg(l.has_value_addition::DOUBLE), avg(l.has_time_extension::DOUBLE)
        FROM labels l JOIN canonical_contracts c USING (contract_id)
        WHERE l.is_closed AND c.signed_at < DATE '{TRAIN_END.isoformat()}'
    """).fetchone()
    return {"has_value_addition": row[0] or 0.0, "has_time_extension": row[1] or 0.0}


# Feature SQL shared by training (assemble_dataset) and serving (serving.scoring), so a
# contract always gets the same features in both places.
FEATURE_SELECT = """
        SELECT
            c.contract_id, c.signed_at, c.buyer_id,
            c.buyer_department, c.buyer_order, c.buyer_sector, c.buyer_branch,
            c.buyer_centralized, c.procurement_method, c.contract_type, c.category_segment,
            c.funding_source,
            CASE WHEN c.award_value >= 0 THEN ln(1 + c.award_value) END AS log_award_value,
            CASE WHEN c.tender_budget >= 0 THEN ln(1 + c.tender_budget) END AS log_tender_budget,
            CASE WHEN c.tender_budget > 0 THEN c.award_value / c.tender_budget END
                AS award_to_budget_ratio,
            c.planned_duration_days,
            CASE WHEN date_diff('day', c.tender_published_at, c.signed_at) >= 0
                 THEN date_diff('day', c.tender_published_at, c.signed_at) END
                AS days_publication_to_signing,
            CASE WHEN date_diff('day', c.signed_at, c.planned_start_at) >= -30
                 THEN date_diff('day', c.signed_at, c.planned_start_at) END
                AS days_signing_to_start,
            c.n_bidders,
            (c.n_bidders = 1)::INT AS single_bidder,
            c.n_responses, c.n_invited, c.n_lots,
            month(c.signed_at) AS signing_month,
            (month(c.signed_at) = 12)::INT AS signed_in_december,
            c.supplier_is_natural_person::INT AS supplier_is_natural_person,
            c.supplier_is_sme::INT AS supplier_is_sme,
            c.supplier_is_group::INT AS supplier_is_group,
            c.advance_payment_enabled::INT AS advance_payment_enabled,
            c.extendable_clause::INT AS extendable_clause,
            hb.buyer_prior_n, hb.buyer_prior_value_addition_rate, hb.buyer_prior_extension_rate,
            hs.supplier_prior_n, hs.supplier_prior_value_addition_rate,
            hs.supplier_prior_extension_rate,
            c.process_found
        FROM canonical_contracts c
        LEFT JOIN history_buyer hb USING (contract_id)
        LEFT JOIN history_supplier hs USING (contract_id)
"""


def feature_frame(con, closed_only: bool) -> pd.DataFrame:
    """Features for every canonical contract; with closed_only, joined to labels and closed."""
    if not closed_only:
        return con.execute(f"{FEATURE_SELECT} ORDER BY c.signed_at, c.contract_id").df()
    return con.execute(f"""
        SELECT f.*, l.has_value_addition, l.has_time_extension
        FROM ({FEATURE_SELECT}) f JOIN labels l USING (contract_id)
        WHERE l.is_closed
        ORDER BY f.signed_at, f.contract_id
    """).df()


def assemble_dataset(raw_dir: Path, as_of: date) -> tuple[pd.DataFrame, DatasetSummary]:
    con = open_audit_db(raw_dir)
    build_canonical(con)
    build_labels(con, as_of)
    rates = _global_rates(con)
    build_history(con, "buyer_id", "buyer", rates)
    build_history(con, "supplier_key", "supplier", rates)

    df = feature_frame(con, closed_only=True)

    summary = DatasetSummary(
        n_rows=len(df),
        n_without_process=int((~df["process_found"].astype(bool)).sum()),
        positive_rate={t: float(df[t].mean()) if len(df) else 0.0 for t in TARGETS},
    )
    return df.drop(columns=["process_found"]), summary


def build_dataset(raw_dir: Path, out_path: Path, as_of: date) -> DatasetSummary:
    df, summary = assemble_dataset(raw_dir, as_of)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return summary
