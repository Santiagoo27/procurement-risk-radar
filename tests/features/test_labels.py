from datetime import date, datetime

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.labels import build_labels

AS_OF = date(2026, 11, 14)


def labels(raw):
    con = open_audit_db(raw)
    build_canonical(con)
    build_labels(con, AS_OF)
    return {r[0]: r[1:] for r in con.execute(
        "SELECT contract_id, is_closed, has_value_addition, has_time_extension, observable_at "
        "FROM labels").fetchall()}


def contract(cid, end="2022-01-01T00:00:00", **kw):
    return {"id_contrato": cid, "fecha_de_firma": "2021-03-01T00:00:00",
            "fecha_de_fin_del_contrato": end, **kw}


def test_text_recovered_addition_counts(make_raw):
    raw = make_raw(contracts=[contract("1"), contract("2")], amendments=[
        {"identificador": "a", "id_contrato": "1", "tipo": "No definido",
         "descripcion": "ADICIONAR el valor del contrato en $1.000.000"},
    ])
    out = labels(raw)
    assert out["1"][1] is True
    assert out["2"][1] is False


def test_open_contract_has_null_labels(make_raw):
    out = labels(make_raw(contracts=[contract("1", end="2026-10-15T00:00:00",
                                              dias_adicionados="10")]))
    assert out["1"][:3] == (False, None, None)


def test_missing_end_date_is_not_closed(make_raw):
    out = labels(make_raw(contracts=[contract("1", end=None)]))
    assert out["1"][0] is False


def test_extension_from_added_days(make_raw):
    out = labels(make_raw(contracts=[contract("1", dias_adicionados="15"),
                                     contract("2", dias_adicionados="0")]))
    assert out["1"][2] is True
    assert out["2"][2] is False


def test_observable_at_is_end_plus_grace(make_raw):
    out = labels(make_raw(contracts=[contract("1", end="2022-01-01T00:00:00")]))
    assert out["1"][3] == datetime(2022, 6, 30)
