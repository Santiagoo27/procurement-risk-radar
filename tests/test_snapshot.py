from datetime import date, datetime

import pyarrow.parquet as pq
import pytest

from procurement_risk import __main__ as cli
from procurement_risk.snapshot import Watermark, take_snapshot
from procurement_risk.sources.socrata import SocrataError

RUN = date(2026, 11, 15)


class FakeClient:
    def __init__(self, pages, fail_after=None):
        self.pages = pages
        self.fail_after = fail_after
        self.wheres = []

    def iter_pages(self, dataset_id, select, where=None):
        self.wheres.append(where)
        for i, p in enumerate(self.pages):
            if self.fail_after is not None and i >= self.fail_after:
                raise SocrataError("boom")
            yield p


def row(cid, updated, value="100"):
    return {"id_contrato": cid, "valor_del_contrato": value, "ultima_actualizacion": updated,
            "fecha_de_fin_del_contrato": "2027-01-01T00:00:00.000", "dias_adicionados": "0",
            "estado_contrato": "En ejecución"}


def test_baseline_when_no_watermark(tmp_path):
    client = FakeClient([[row("a", "2026-11-14T10:00:00.000")]])
    path, wm = take_snapshot(client, tmp_path, Watermark(None), RUN)
    assert client.wheres == [None]
    assert path.name == "baseline-2026-11-15.parquet"
    assert wm.last_updated == datetime(2026, 11, 14, 10)


def test_full_flag_forces_baseline(tmp_path):
    client = FakeClient([[row("a", "2026-11-14T10:00:00.000")]])
    path, _ = take_snapshot(client, tmp_path, Watermark(datetime(2026, 11, 1)), RUN, full=True)
    assert client.wheres == [None]
    assert path.name.startswith("baseline-")


def test_incremental_uses_watermark(tmp_path):
    client = FakeClient([[row("a", "2026-11-14T10:00:00.000")]])
    path, _ = take_snapshot(client, tmp_path, Watermark(datetime(2026, 11, 14)), RUN)
    assert "ultima_actualizacion > '2026-11-14T00:00:00" in client.wheres[0]
    assert path.name == "changes-2026-11-15.parquet"


def test_dedupes_same_contract_same_update(tmp_path):
    client = FakeClient([
        [row("a", "2026-11-14T10:00:00.000"), row("a", "2026-11-14T11:00:00.000")],
        [row("a", "2026-11-14T10:00:00.000")],
    ])
    path, _ = take_snapshot(client, tmp_path, Watermark(datetime(2026, 11, 1)), RUN)
    rows = pq.read_table(path).to_pylist()
    assert len(rows) == 2
    assert set(rows[0]) == {"id_contrato", "valor_del_contrato", "fecha_de_fin_del_contrato",
                            "dias_adicionados", "estado_contrato", "ultima_actualizacion",
                            "snapshot_date"}


def test_watermark_advances_to_max_seen_ignoring_nulls(tmp_path):
    client = FakeClient([[row("a", "2026-11-14T10:00:00.000"), row("b", None),
                          row("c", "2026-11-14T12:30:00.000")]])
    _, wm = take_snapshot(client, tmp_path, Watermark(datetime(2026, 11, 1)), RUN)
    assert wm.last_updated == datetime(2026, 11, 14, 12, 30)


def test_no_changes_returns_none(tmp_path):
    old = Watermark(datetime(2026, 11, 14))
    path, wm = take_snapshot(FakeClient([]), tmp_path, old, RUN)
    assert path is None
    assert wm == old
    assert list(tmp_path.iterdir()) == []


def test_watermark_roundtrip(tmp_path):
    p = tmp_path / "wm.json"
    assert Watermark.load(p) == Watermark(None)
    Watermark(datetime(2026, 11, 14, 1, 2, 3, 456000)).save(p)
    assert Watermark.load(p) == Watermark(datetime(2026, 11, 14, 1, 2, 3, 456000))


def test_failure_does_not_advance_watermark(tmp_path, monkeypatch):
    wm_path = tmp_path / "watermark.json"
    Watermark(datetime(2026, 11, 14)).save(wm_path)
    before = wm_path.read_text()
    client = FakeClient([[row("a", "2026-11-14T10:00:00.000")], [row("b", "x")]], fail_after=1)
    monkeypatch.setattr(cli, "SocrataClient", lambda *a, **k: client)
    with pytest.raises(SocrataError):
        cli.main(["snapshot", "--watermark", str(wm_path), "--out", str(tmp_path),
                  "--run-date", "2026-11-15"])
    assert wm_path.read_text() == before
    assert list(tmp_path.glob("*.parquet")) == []
