"""Thresholds for the automated pipelines (Phase 4). Kept in one place on purpose."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityThresholds:
    min_process_rows: int = 1_000_000
    max_staleness_days: int = 14
    max_null_share: float = 0.05
    min_count_ratio: float = 0.95
    # Absolute floors: a truncated download must fail even without a previous run to compare.
    min_contract_rows: int = 5_000_000
    min_amendment_rows: int = 7_000_000


@dataclass(frozen=True)
class PromotionGate:
    """Applied to each target on its own: a target's new model replaces the production one
    only if it gains PR-AUC and keeps calibration. Otherwise that target keeps its model."""
    max_brier_ratio: float = 1.02
    min_pr_auc_gain: float = 0.002


@dataclass(frozen=True)
class MonitoringThresholds:
    psi_shifted: float = 0.2
    min_rows: int = 500
    current_window_days: int = 90
    realized_window_days: int = 180
    realized_pr_auc_drop: float = 0.03


# Inputs that drift by construction: calendar features follow the season and the election
# cycle of the current window, and history counts grow as the archive accumulates. Reported,
# never alerted on.
EXPECTED_DRIFT = frozenset({"signing_month", "signed_in_december", "buyer_prior_n",
                            "supplier_prior_n", "signed_in_restriction",
                            "planned_end_in_restriction", "days_end_to_next_election"})

QUALITY = QualityThresholds()
GATE = PromotionGate()
MONITORING = MonitoringThresholds()
SEVERITY_MIN_N = 100
