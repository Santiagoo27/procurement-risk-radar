"""Thresholds for the automated pipelines (Phase 4). Kept in one place on purpose."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityThresholds:
    min_process_rows: int = 1_000_000
    max_staleness_days: int = 14
    max_null_share: float = 0.05
    min_count_ratio: float = 0.95


@dataclass(frozen=True)
class PromotionGate:
    max_pr_auc_drop: float = 0.005
    max_brier_ratio: float = 1.02
    min_pr_auc_gain: float = 0.002


@dataclass(frozen=True)
class MonitoringThresholds:
    psi_shifted: float = 0.2
    min_rows: int = 500
    current_window_days: int = 90
    realized_window_days: int = 180
    realized_pr_auc_drop: float = 0.03


QUALITY = QualityThresholds()
GATE = PromotionGate()
MONITORING = MonitoringThresholds()
SEVERITY_MIN_N = 100
