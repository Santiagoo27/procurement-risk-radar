from datetime import date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from procurement_risk.ops.severity import load_history, summary, value_changes


def write(path, rows, snapshot):
    table = pa.table({
        "id_contrato": [r[0] for r in rows],
        "valor_del_contrato": [float(r[1]) for r in rows],
        "ultima_actualizacion": [datetime(2026, 11, r[2]) for r in rows],
        "snapshot_date": [snapshot] * len(rows),
    })
    pq.write_table(table, path)


@pytest.fixture
def archive(tmp_path):
    write(tmp_path / "baseline-2026-11-14-174727Z.parquet",
          [("A", 100, 1), ("B", 200, 1), ("C", 300, 1), ("D", 0, 1)], date(2026, 11, 14))
    write(tmp_path / "changes-2026-11-16-070000Z.parquet",
          [("A", 130, 15), ("B", 150, 15), ("D", 50, 15)], date(2026, 11, 16))
    write(tmp_path / "changes-2026-11-18-070000Z.parquet",
          [("A", 160, 17)], date(2026, 11, 18))
    return tmp_path


def test_first_and_latest_values_per_contract(archive):
    changes = value_changes(load_history(archive)).set_index("id_contrato")
    assert changes.loc["A", "first_value"] == 100
    assert changes.loc["A", "latest_value"] == 160


def test_only_increases_count(archive):
    changes = value_changes(load_history(archive))
    assert set(changes["id_contrato"]) == {"A"}  # B decreased, C unchanged, D started at 0


def test_increase_pct(archive):
    changes = value_changes(load_history(archive)).set_index("id_contrato")
    assert changes.loc["A", "increase_pct"] == pytest.approx(0.6)


def test_summary_not_enough_data_below_min_n(archive):
    out = summary(load_history(archive), min_n=100)
    assert out["n_contracts_observed"] == 4
    assert out["n_increased"] == 1
    assert out["median_increase_pct"] is None
    assert "fewer than 100" in out["reason"]
    assert out["since"] == "2026-11-14"


def test_summary_with_enough_data(archive):
    out = summary(load_history(archive), min_n=1)
    assert out["median_increase_pct"] == pytest.approx(0.6)
    assert out["share_over_30pct"] == pytest.approx(1.0)
    assert out["reason"] is None
