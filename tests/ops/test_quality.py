import json
from datetime import date

import pytest

from procurement_risk.ops.config import QualityThresholds
from procurement_risk.ops.quality import check_raw

RUN = date(2026, 11, 15)
SMALL = QualityThresholds(min_process_rows=3, max_staleness_days=14, max_null_share=0.05,
                          min_count_ratio=0.95)


def contracts(n, signed="2026-11-10T00:00:00", **kw):
    return [{"id_contrato": f"C{i}", "fecha_de_firma": signed, "codigo_entidad": "E1",
             "valor_del_contrato": "100", **kw} for i in range(n)]


def processes(n):
    return [{"id_del_portafolio": f"P{i}"} for i in range(n)]


def amendments(n):
    return [{"identificador": f"A{i}", "id_contrato": "C0"} for i in range(n)]


def names(report):
    return {c.name: c for c in report.checks}


def test_healthy_data_passes(make_raw):
    raw = make_raw(contracts=contracts(20), amendments=amendments(5), processes=processes(10))
    report = check_raw(raw, previous=None, run_date=RUN, thresholds=SMALL)
    assert report.passed, report.to_markdown()
    assert report.counts == {"contracts": 20, "amendments": 5, "processes": 10}


def test_truncated_processes_fail(make_raw):
    raw = make_raw(contracts=contracts(20), amendments=amendments(5), processes=processes(2))
    report = check_raw(raw, previous=None, run_date=RUN, thresholds=SMALL)
    assert not report.passed
    failed = [c for c in report.checks if not c.passed]
    assert any("processes" in c.name for c in failed)
    assert "processes" in report.to_markdown()


def test_row_drop_against_previous_fails(make_raw):
    raw = make_raw(contracts=contracts(20), amendments=amendments(5), processes=processes(10))
    previous = {"contracts": 100, "amendments": 5, "processes": 10}
    report = check_raw(raw, previous=previous, run_date=RUN, thresholds=SMALL)
    assert not names(report)["contracts row count vs previous"].passed


def test_stale_data_fails(make_raw):
    raw = make_raw(contracts=contracts(20, signed="2026-09-01T00:00:00"),
                   amendments=amendments(5), processes=processes(10))
    report = check_raw(raw, previous=None, run_date=RUN, thresholds=SMALL)
    assert not names(report)["contracts are recent"].passed


def test_null_share_fails(make_raw):
    rows = contracts(10) + contracts(10, codigo_entidad=None)
    raw = make_raw(contracts=rows, amendments=amendments(5), processes=processes(10))
    report = check_raw(raw, previous=None, run_date=RUN, thresholds=SMALL)
    assert not names(report)["contracts.codigo_entidad nulls"].passed


def test_cli_exit_code_4_on_failure(make_raw, tmp_path, monkeypatch):
    from procurement_risk import __main__ as cli
    from procurement_risk.ops import config

    monkeypatch.setattr(config, "QUALITY", SMALL)
    raw = make_raw(contracts=contracts(20), amendments=amendments(5), processes=processes(1))
    out = tmp_path / "quality.json"
    with pytest.raises(SystemExit) as exc:
        cli.main(["check-quality", "--raw", str(raw), "--out", str(out),
                  "--run-date", RUN.isoformat()])
    assert exc.value.code == 4
    assert json.loads(out.read_text(encoding="utf-8"))["passed"] is False
