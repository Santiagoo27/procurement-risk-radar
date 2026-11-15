"""Data-quality checks on a fresh SECOP download, run before anything is published.

The 2026-11-15 refresh of the processes dataset (truncated to 1,000 rows) is the kind of
partial outage these checks must stop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.ops.config import QualityThresholds

REQUIRED_CONTRACT_COLUMNS = ("id_contrato", "fecha_de_firma", "codigo_entidad",
                             "valor_del_contrato")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class QualityReport:
    run_date: str
    counts: dict[str, int]
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict:
        return {"run_date": self.run_date, "passed": self.passed, "counts": self.counts,
                "checks": [asdict(c) for c in self.checks]}

    def to_markdown(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"### Data quality {status} ({self.run_date})", "",
                 "| Check | Result | Detail |", "|---|---|---|"]
        lines += [f"| {c.name} | {'ok' if c.passed else 'FAIL'} | {c.detail} |"
                  for c in self.checks]
        return "\n".join(lines) + "\n"


def check_raw(raw_dir: Path | list[Path], previous: dict | None, run_date: date,
              thresholds: QualityThresholds | None = None) -> QualityReport:
    from procurement_risk.ops import config

    t = thresholds or config.QUALITY
    con = open_audit_db(raw_dir)
    counts = {name: int(con.execute(f"SELECT count(*) FROM {name}").fetchone()[0])
              for name in ("contracts", "amendments", "processes")}
    report = QualityReport(run_date=run_date.isoformat(), counts=counts)
    add = report.checks.append

    for name, n in counts.items():
        add(Check(f"{name} not empty", n > 0, f"{n:,} rows"))
    add(Check("processes row count", counts["processes"] >= t.min_process_rows,
              f"{counts['processes']:,} rows (minimum {t.min_process_rows:,})"))

    if previous:
        for name, n in counts.items():
            before = int(previous.get(name, 0))
            ok = before == 0 or n >= t.min_count_ratio * before
            add(Check(f"{name} row count vs previous", ok,
                      f"{n:,} now vs {before:,} last run (minimum {t.min_count_ratio:.0%})"))

    latest = con.execute("SELECT max(fecha_de_firma) FROM contracts").fetchone()[0]
    cutoff = run_date - timedelta(days=t.max_staleness_days)
    recent = latest is not None and latest.date() >= cutoff
    add(Check("contracts are recent", recent,
              f"latest signing date {latest.date() if latest else None} (cutoff {cutoff})"))

    total = max(counts["contracts"], 1)
    for col in REQUIRED_CONTRACT_COLUMNS:
        nulls = int(con.execute(f"SELECT count(*) FROM contracts WHERE {col} IS NULL")
                    .fetchone()[0])
        share = nulls / total
        add(Check(f"contracts.{col} nulls", share <= t.max_null_share,
                  f"{share:.1%} null (maximum {t.max_null_share:.0%})"))
    con.close()
    return report
