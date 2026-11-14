"""Shared helpers: build tiny raw SECOP datasets as Parquet in a temp directory."""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

from procurement_risk import config
from procurement_risk.parsing import to_arrow

COLUMNS = {
    "contracts": (*config.CONTRACT_COLUMNS, "supplier_is_natural_person"),
    "amendments": config.AMENDMENT_COLUMNS,
    "processes": config.PROCESS_COLUMNS,
}


@pytest.fixture
def make_raw(tmp_path):
    """Return a function writing contracts/amendments/processes rows; returns the raw dir."""

    def _make(contracts=(), amendments=(), processes=()) -> Path:
        for name, rows in (("contracts", contracts), ("amendments", amendments),
                           ("processes", processes)):
            d = tmp_path / "raw" / name
            d.mkdir(parents=True, exist_ok=True)
            pq.write_table(to_arrow(list(rows), COLUMNS[name]), d / "part-00000.parquet")
        return tmp_path / "raw"

    return _make
