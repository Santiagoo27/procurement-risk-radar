from datetime import date

import pyarrow.parquet as pq
import pytest

from procurement_risk import config
from procurement_risk.audit.metrics import (
    bidder_coverage,
    closure_states,
    end_date_vs_duration,
    hidden_value_additions,
    label_rates_by_year,
    open_audit_db,
    value_vs_award,
)
from procurement_risk.parsing import to_arrow

CONTRACT_COLS = (*config.CONTRACT_COLUMNS, "supplier_is_natural_person")


def write(raw, name, rows, columns):
    d = raw / name
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(to_arrow(rows, columns), d / "part-00000.parquet")


def c(cid, signed="2021-03-01T00:00:00", **kw):
    return {"id_contrato": cid, "fecha_de_firma": signed, "dias_adicionados": "0", **kw}


def a(aid, cid, tipo, desc="x"):
    return {"identificador": aid, "id_contrato": cid, "tipo": tipo, "descripcion": desc}


@pytest.fixture
def raw(tmp_path):
    return tmp_path


def test_label_rates_by_year(raw):
    write(raw, "contracts", [
        c("1"), c("2", dias_adicionados="10"), c("3", dias_adicionados="5"), c("4"),
        c("5", signed="2022-02-01T00:00:00"),
    ], CONTRACT_COLS)
    write(raw, "amendments", [a("x", "1", "Adicion en el valor"),
                              a("y", "1", "Adicion en el valor")], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [], config.PROCESS_COLUMNS)
    rates = label_rates_by_year(open_audit_db(raw))
    y2021 = next(r for r in rates if r["year"] == 2021)
    assert y2021["n_contracts"] == 4
    assert y2021["value_addition_rate"] == 0.25
    assert y2021["extension_rate"] == 0.5


def test_hidden_share(raw):
    write(raw, "contracts", [c("1"), c("2")], CONTRACT_COLS)
    write(raw, "amendments", [
        a("e1", "1", "Adicion en el valor"), a("e2", "1", "Adicion en el valor"),
        a("e3", "2", "Adicion en el valor"),
        a("h1", "2", "Modificacion General", "ADICIÓN EN VALOR AL CONTRATO"),
        a("n1", "2", "No definido", "ACTA DE LIQUIDACION"),
        a("o1", "999", "Modificacion General", "adición en valor (not in sample)"),
    ], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [], config.PROCESS_COLUMNS)
    out = hidden_value_additions(open_audit_db(raw))
    assert out["explicit"] == 3
    assert out["hidden_matches"] == 1
    assert out["hidden_share"] == 0.25
    assert out["sample"] == ["ADICIÓN EN VALOR AL CONTRATO"]


def test_value_vs_award_ratio(raw):
    write(raw, "contracts", [
        c("1", proceso_de_compra="P1", valor_del_contrato="150"),
        c("2", proceso_de_compra="P2", valor_del_contrato="100"),
    ], CONTRACT_COLS)
    write(raw, "amendments", [a("x", "1", "Adicion en el valor")], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [
        {"id_del_portafolio": "P1", "valor_total_adjudicacion": "100"},
        {"id_del_portafolio": "P2", "valor_total_adjudicacion": "100"},
    ], config.PROCESS_COLUMNS)
    out = value_vs_award(open_audit_db(raw))
    assert out["join_rate"] == 1.0
    assert out["median_ratio_with_addition"] == 1.5
    assert out["median_ratio_without_addition"] == 1.0


def test_end_date_vs_duration(raw):
    write(raw, "contracts", [
        c("1", duraci_n_del_contrato="30 Dia(s)", dias_adicionados="30",
          fecha_de_inicio_del_contrato="2021-01-01T00:00:00",
          fecha_de_fin_del_contrato="2021-03-02T00:00:00"),
        c("2", duraci_n_del_contrato="1 Mes(es)", dias_adicionados="30",
          fecha_de_inicio_del_contrato="2021-01-01T00:00:00",
          fecha_de_fin_del_contrato="2021-01-31T00:00:00"),
        c("3", duraci_n_del_contrato="No definido", dias_adicionados="5",
          fecha_de_inicio_del_contrato="2021-01-01T00:00:00",
          fecha_de_fin_del_contrato="2021-01-31T00:00:00"),
        c("4", duraci_n_del_contrato="30 Dia(s)", dias_adicionados="0"),
    ], CONTRACT_COLS)
    write(raw, "amendments", [], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [], config.PROCESS_COLUMNS)
    out = end_date_vs_duration(open_audit_db(raw))
    assert out["n"] == 3
    assert out["share_end_date_moved"] == 0.5  # of the 2 parseable
    assert out["share_duration_unparseable"] == pytest.approx(1 / 3)


def test_closure_states(raw):
    write(raw, "contracts", [
        c("1", estado_contrato="terminado", fecha_de_fin_del_contrato="2021-01-01T00:00:00"),
        c("2", estado_contrato="terminado", fecha_de_fin_del_contrato="2026-10-01T00:00:00"),
        c("3", estado_contrato="En ejecución", fecha_de_fin_del_contrato="2027-01-01T00:00:00"),
    ], CONTRACT_COLS)
    write(raw, "amendments", [], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [], config.PROCESS_COLUMNS)
    out = {r["estado_contrato"]: r for r in closure_states(open_audit_db(raw), date(2026, 11, 14))}
    assert out["terminado"]["n"] == 2
    assert out["terminado"]["share_end_before_as_of_minus_180d"] == 0.5
    assert out["En ejecución"]["share_end_before_as_of_minus_180d"] == 0.0


def test_bidder_coverage(raw):
    write(raw, "contracts", [c("1", proceso_de_compra="P1"), c("2", proceso_de_compra="P2"),
                             c("3", proceso_de_compra="NOPE")], CONTRACT_COLS)
    write(raw, "amendments", [], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [
        {"id_del_portafolio": "P1", "proveedores_unicos_con": "1",
         "respuestas_al_procedimiento": "1"},
        {"id_del_portafolio": "P2", "proveedores_unicos_con": None,
         "respuestas_al_procedimiento": "3"},
    ], config.PROCESS_COLUMNS)
    out = bidder_coverage(open_audit_db(raw))
    assert out["join_rate"] == pytest.approx(2 / 3)
    assert out["unique_bidders_coverage"] == 0.5
    assert out["responses_coverage"] == 1.0
    assert out["single_bidder_share"] == 1.0




def test_hidden_contracts_ignores_null_ids(raw):
    write(raw, "contracts", [c("1"), c("2")], CONTRACT_COLS)
    write(raw, "amendments", [
        a("e1", "1", "Adicion en el valor"), a("e0", None, "Adicion en el valor"),
        a("h1", "2", "Modificacion General", "ADICIÓN EN VALOR AL CONTRATO"),
    ], config.AMENDMENT_COLUMNS)
    write(raw, "processes", [], config.PROCESS_COLUMNS)
    assert hidden_value_additions(open_audit_db(raw))["hidden_contracts"] == 1
