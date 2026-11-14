from datetime import date

import pytest

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.history import build_history
from procurement_risk.features.labels import build_labels

GLOBAL = {"has_value_addition": 0.1, "has_time_extension": 0.2}


def history(raw, key="buyer_id", prefix="buyer"):
    con = open_audit_db(raw)
    build_canonical(con)
    build_labels(con, date(2026, 11, 14))
    build_history(con, key, prefix, GLOBAL, prior_strength=20.0)
    return {r[0]: r[1:] for r in con.execute(
        f"SELECT contract_id, {prefix}_prior_n, {prefix}_prior_value_addition_rate, "
        f"{prefix}_prior_extension_rate FROM history_{prefix}").fetchall()}


def contract(cid, signed, end, entity="E1", supplier=None, added="0"):
    return {"id_contrato": cid, "fecha_de_firma": signed, "fecha_de_fin_del_contrato": end,
            "codigo_entidad": entity, "codigo_proveedor": supplier, "dias_adicionados": added}


def test_history_excludes_own_label(make_raw):
    raw = make_raw(contracts=[contract("1", "2021-01-01T00:00:00", "2021-02-01T00:00:00")])
    assert history(raw)["1"][0] == 0


def test_history_excludes_not_yet_observable(make_raw):
    # A ends 2021-12-03 -> observable 2022-06-01 (end + 180 days).
    raw = make_raw(contracts=[
        contract("A", "2021-06-01T00:00:00", "2021-12-03T00:00:00", added="5"),
        contract("B", "2022-06-01T00:00:00", "2022-12-01T00:00:00"),
        contract("C", "2022-06-02T00:00:00", "2022-12-01T00:00:00"),
    ])
    out = history(raw)
    assert out["B"][0] == 0
    assert out["C"][0] == 1
    assert out["C"][2] == pytest.approx((1 + 20 * 0.2) / 21)


def test_history_separates_keys(make_raw):
    raw = make_raw(contracts=[
        contract("X1", "2020-01-01T00:00:00", "2020-02-01T00:00:00", entity="X"),
        contract("Y1", "2022-01-01T00:00:00", "2022-02-01T00:00:00", entity="Y"),
    ])
    assert history(raw)["Y1"][0] == 0


def test_rate_is_smoothed(make_raw):
    add = {"tipo": "Adicion en el valor"}
    raw = make_raw(
        contracts=[
            contract("1", "2019-01-01T00:00:00", "2019-02-01T00:00:00"),
            contract("2", "2019-01-01T00:00:00", "2019-02-01T00:00:00"),
            contract("3", "2022-01-01T00:00:00", "2022-02-01T00:00:00"),
        ],
        amendments=[{"identificador": "a1", "id_contrato": "1", **add},
                    {"identificador": "a2", "id_contrato": "2", **add}],
    )
    out = history(raw)["3"]
    assert out[0] == 2
    assert out[1] == pytest.approx((2 + 20 * 0.1) / 22)


def test_null_supplier_key_gets_global_rate(make_raw):
    raw = make_raw(contracts=[
        contract("1", "2019-01-01T00:00:00", "2019-02-01T00:00:00", supplier=None, added="3"),
        contract("2", "2022-01-01T00:00:00", "2022-02-01T00:00:00", supplier=None),
    ])
    out = history(raw, key="supplier_key", prefix="supplier")["2"]
    assert out == (0, pytest.approx(0.1), pytest.approx(0.2))


def test_open_contracts_never_become_events(make_raw):
    raw = make_raw(contracts=[
        contract("open", "2026-01-01T00:00:00", "2026-10-01T00:00:00", added="9"),
        contract("later", "2026-11-01T00:00:00", "2027-01-01T00:00:00"),
    ])
    assert history(raw)["later"][0] == 0


def test_end_before_signing_does_not_leak(make_raw):
    # Bad source data: end date long before the signing date.
    raw = make_raw(contracts=[
        contract("EARLY", "2021-09-01T00:00:00", "2022-01-01T00:00:00"),
        contract("SELF", "2022-06-01T00:00:00", "2021-01-01T00:00:00", added="9"),
    ])
    out = history(raw)
    assert out["SELF"][0] == 0
    assert out["EARLY"][0] == 0


def test_late_amendment_delays_observability(make_raw):
    # A ends 2021-01-01 (observable 2021-06-30) but its addition is recorded 2022-03-01.
    raw = make_raw(
        contracts=[
            contract("A", "2020-06-01T00:00:00", "2021-01-01T00:00:00"),
            contract("B", "2021-12-01T00:00:00", "2022-06-01T00:00:00"),
            contract("C", "2022-04-01T00:00:00", "2022-06-01T00:00:00"),
        ],
        amendments=[{"identificador": "x", "id_contrato": "A", "tipo": "Adicion en el valor",
                     "fecharegistro": "2022-03-01T00:00:00"}],
    )
    out = history(raw)
    assert out["B"][0] == 0
    assert out["C"][0] == 1
