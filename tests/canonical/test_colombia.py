import pytest

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical


def canonical(raw):
    con = open_audit_db(raw)
    build_canonical(con)
    return con


def contract(cid, **kw):
    return {"id_contrato": cid, "fecha_de_firma": "2021-03-01T00:00:00",
            "codigo_entidad": "E1", **kw}


def one(con, sql):
    return con.execute(sql).fetchone()


def test_award_value_falls_back_to_budget(make_raw):
    raw = make_raw(
        contracts=[contract("1", proceso_de_compra="P1")],
        processes=[{"id_del_portafolio": "P1", "valor_total_adjudicacion": None,
                    "precio_base": "500"}],
    )
    con = canonical(raw)
    assert one(con, "SELECT award_value, tender_budget FROM canonical_contracts") == (500.0, 500.0)


def test_missing_process_keeps_contract(make_raw):
    raw = make_raw(contracts=[contract("1", proceso_de_compra="NOPE")])
    con = canonical(raw)
    assert one(con, "SELECT count(*), any_value(award_value), any_value(n_bidders) "
                    "FROM canonical_contracts") == (1, None, None)


@pytest.mark.parametrize("value,unit,expected", [
    ("3", "Meses", 90.0), ("2", "Semana(s)", 14.0), ("1", "Año", 365.0),
    ("10", "Quincenas", None), ("0", "Dias", None), ("15", "Días", 15.0),
    ("4000", "Dias", None), ("11", "Años", None),
])
def test_duration_units(make_raw, value, unit, expected):
    raw = make_raw(
        contracts=[contract("1", proceso_de_compra="P1")],
        processes=[{"id_del_portafolio": "P1", "duracion": value, "unidad_de_duracion": unit}],
    )
    got = one(canonical(raw), "SELECT planned_duration_days FROM canonical_contracts")[0]
    assert got == (pytest.approx(expected) if expected is not None else None)


@pytest.mark.parametrize("code,segment", [("V1.80111600", "80"), (None, None)])
def test_category_segment(make_raw, code, segment):
    raw = make_raw(contracts=[contract("1", codigo_de_categoria_principal=code)])
    assert one(canonical(raw), "SELECT category_segment FROM canonical_contracts")[0] == segment


def test_amendment_kinds(make_raw):
    raw = make_raw(
        contracts=[contract("1")],
        amendments=[
            {"identificador": "a", "id_contrato": "1", "tipo": "Adicion en el valor"},
            {"identificador": "b", "id_contrato": "1", "tipo": "Modificacion General",
             "descripcion": "ADICIÓN EN VALOR"},
            {"identificador": "c", "id_contrato": "1", "tipo": "Modificacion General",
             "descripcion": "Prórroga"},
            {"identificador": "d", "id_contrato": "1", "tipo": "Extension"},
        ],
    )
    rows = dict(canonical(raw).execute(
        "SELECT amendment_id, kind FROM canonical_amendments").fetchall())
    assert rows == {"a": "value_addition", "b": "value_addition_text", "c": "other",
                    "d": "extension"}


def test_no_excluded_columns_leak_as_features(make_raw):
    con = canonical(make_raw(contracts=[contract("1")]))
    cols = {r[0] for r in con.execute("DESCRIBE canonical_contracts").fetchall()}
    assert {"valor_del_contrato", "estado_contrato", "proveedor_adjudicado"}.isdisjoint(cols)
    assert {"signed_at", "buyer_id", "supplier_key", "current_end_at", "added_days"} <= cols
