from datetime import datetime

import pyarrow as pa

from procurement_risk.parsing import (
    parse_bool,
    parse_int,
    parse_money,
    parse_timestamp,
    to_arrow,
)


def test_parse_handles_garbage():
    assert parse_money("No Definido") is None
    assert parse_money("1500000") == 1500000.0
    assert parse_money("1500000.50") == 1500000.5
    assert parse_money(None) is None
    assert parse_timestamp("2021-03-04T00:00:00.000") == datetime(2021, 3, 4)
    assert parse_timestamp("2021-03-04T10:20:30") == datetime(2021, 3, 4, 10, 20, 30)
    assert parse_timestamp("2021-03-04") == datetime(2021, 3, 4)
    assert parse_timestamp("31/12/2021") is None
    assert parse_timestamp("") is None
    assert parse_int(None) is None
    assert parse_int("12") == 12
    assert parse_int("12.0") == 12
    assert parse_int("abc") is None
    assert parse_bool("Sí") is True
    assert parse_bool("Si") is True
    assert parse_bool("No") is False
    assert parse_bool("No Definido") is None
    assert parse_bool(True) is True


def test_to_arrow_types():
    rows = [
        {"valor_del_contrato": "100", "fecha_de_firma": "2021-01-02T00:00:00.000",
         "dias_adicionados": "3", "es_pyme": "No", "nombre_entidad": "X"},
        {"valor_del_contrato": "No Definido", "fecha_de_firma": None,
         "dias_adicionados": None, "es_pyme": None, "nombre_entidad": None},
    ]
    table = to_arrow(rows, ["valor_del_contrato", "fecha_de_firma", "dias_adicionados",
                            "es_pyme", "nombre_entidad"])
    assert table.schema.field("valor_del_contrato").type == pa.float64()
    assert pa.types.is_timestamp(table.schema.field("fecha_de_firma").type)
    assert table.schema.field("dias_adicionados").type == pa.int64()
    assert table.schema.field("es_pyme").type == pa.bool_()
    assert table.schema.field("nombre_entidad").type == pa.string()
    assert table.column("valor_del_contrato").to_pylist() == [100.0, None]


def test_parse_rejects_non_finite_and_huge_numbers():
    assert parse_money("nan") is None
    assert parse_money("inf") is None
    assert parse_money("-Infinity") is None
    assert parse_int("1e400") is None
    assert parse_int("inf") is None
    assert parse_int("99999999999999999999") is None
    table = to_arrow([{"dias_adicionados": "99999999999999999999"}], ["dias_adicionados"])
    assert table.column("dias_adicionados").to_pylist() == [None]
