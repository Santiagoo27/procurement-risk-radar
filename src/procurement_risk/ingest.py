"""Download SECOP II datasets into typed, PII-safe Parquet files."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import pyarrow.parquet as pq

from procurement_risk import config
from procurement_risk.parsing import to_arrow
from procurement_risk.privacy import project, scrub_contract


class PageSource(Protocol):
    def iter_pages(
        self, dataset_id: str, select: Sequence[str], where: str | None = None
    ) -> Iterable[list[dict[str, str]]]: ...


def _date_range(column: str, start: date, end: date) -> str:
    return f"{column} >= '{start.isoformat()}T00:00:00' AND {column} < '{end.isoformat()}T00:00:00'"


def _write_pages(
    pages: Iterable[list[dict[str, str]]],
    out_dir: Path,
    columns: Sequence[str],
    transform: Callable[[dict[str, str]], dict[str, Any]],
) -> Path:
    """Write all pages to a temporary sibling directory and swap it in only on success."""
    tmp_dir = out_dir.with_name(out_dir.name + ".tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for i, rows in enumerate(pages):
            table = to_arrow([transform(r) for r in rows], columns)
            pq.write_table(table, tmp_dir / f"part-{i:05d}.parquet")
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    if out_dir.exists():
        shutil.rmtree(out_dir)
    tmp_dir.rename(out_dir)
    return out_dir


def ingest_contracts(
    client: PageSource, out_dir: Path, signed_from: date, signed_to: date, salt: bytes
) -> Path:
    pages = client.iter_pages(
        config.CONTRACTS_ID,
        select=config.CONTRACT_COLUMNS,
        where=_date_range("fecha_de_firma", signed_from, signed_to),
    )
    columns = (*config.CONTRACT_COLUMNS, "supplier_is_natural_person")
    return _write_pages(pages, out_dir / "contracts", columns, lambda r: scrub_contract(r, salt))


def ingest_amendments(client: PageSource, out_dir: Path) -> Path:
    pages = client.iter_pages(config.AMENDMENTS_ID, select=config.AMENDMENT_COLUMNS)
    return _write_pages(
        pages, out_dir / "amendments", config.AMENDMENT_COLUMNS,
        lambda r: project(r, config.AMENDMENT_COLUMNS),
    )


def ingest_processes(
    client: PageSource, out_dir: Path, published_from: date, published_to: date
) -> Path:
    pages = client.iter_pages(
        config.PROCESSES_ID,
        select=config.PROCESS_COLUMNS,
        where=_date_range("fecha_de_publicacion_del", published_from, published_to),
    )
    return _write_pages(
        pages, out_dir / "processes", config.PROCESS_COLUMNS,
        lambda r: project(r, config.PROCESS_COLUMNS),
    )
