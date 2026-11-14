"""Nightly snapshot archive of contract values and end dates.

Amendment amounts are not published by SECOP, so the only way to measure them later is to
record how `valor_del_contrato` and end dates change over time. This history cannot be
backfilled; it starts the first day this job runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from procurement_risk import config
from procurement_risk.ingest import PageSource
from procurement_risk.parsing import to_arrow
from procurement_risk.privacy import project


@dataclass(frozen=True)
class Watermark:
    last_updated: datetime | None

    @classmethod
    def load(cls, path: Path) -> Watermark:
        if not path.exists():
            return cls(None)
        value = json.loads(path.read_text(encoding="utf-8")).get("last_updated")
        return cls(datetime.fromisoformat(value) if value else None)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        value = self.last_updated.isoformat(timespec="milliseconds") if self.last_updated else None
        path.write_text(json.dumps({"last_updated": value}), encoding="utf-8")


def take_snapshot(
    client: PageSource,
    out_dir: Path,
    watermark: Watermark,
    run_date: date,
    full: bool = False,
) -> tuple[Path | None, Watermark]:
    """Fetch rows updated after the watermark (or everything) and write one Parquet file.

    Nothing is written unless every page was fetched; exceptions propagate.
    """
    baseline = full or watermark.last_updated is None
    where = None
    if not baseline:
        where = (
            "ultima_actualizacion > "
            f"'{watermark.last_updated.isoformat(timespec='milliseconds')}'"
        )

    tables = [
        to_arrow([project(r, config.SNAPSHOT_COLUMNS) for r in page], config.SNAPSHOT_COLUMNS)
        for page in client.iter_pages(config.CONTRACTS_ID, config.SNAPSHOT_COLUMNS, where)
    ]
    if not tables:
        return None, watermark

    combined = pa.concat_tables(tables)
    deduped = duckdb.sql(
        "SELECT DISTINCT ON (id_contrato, ultima_actualizacion) *, "
        f"DATE '{run_date.isoformat()}' AS snapshot_date FROM combined"
    ).arrow()
    if isinstance(deduped, pa.RecordBatchReader):
        deduped = deduped.read_all()

    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = "baseline" if baseline else "changes"
    path = out_dir / f"{prefix}-{run_date.isoformat()}.parquet"
    pq.write_table(deduped, path)

    seen = pc.max(combined.column("ultima_actualizacion")).as_py()
    candidates = [t for t in (seen, None if baseline else watermark.last_updated) if t]
    return path, Watermark(max(candidates) if candidates else watermark.last_updated)
