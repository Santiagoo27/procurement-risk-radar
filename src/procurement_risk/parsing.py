"""Convert Socrata string values into typed Arrow columns.

Socrata returns every field as a string. Unparseable values become null instead of failing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pyarrow as pa

MONEY_COLUMNS = frozenset({
    "valor_del_contrato", "valor_de_pago_adelantado", "valor_facturado", "valor_pagado",
    "precio_base", "valor_total_adjudicacion",
})
INT_COLUMNS = frozenset({
    "dias_adicionados", "proveedores_invitados", "proveedores_que_manifestaron",
    "respuestas_al_procedimiento", "proveedores_unicos_con", "numero_de_lotes", "duracion",
})
BOOL_COLUMNS = frozenset({
    "es_grupo", "es_pyme", "habilita_pago_adelantado", "el_contrato_puede_ser_prorrogado",
    "espostconflicto", "liquidaci_n", "adjudicado", "supplier_is_natural_person",
})
TIMESTAMP_COLUMNS = frozenset({
    "fecha_de_firma", "fecha_de_inicio_del_contrato", "fecha_de_fin_del_contrato",
    "ultima_actualizacion", "fecharegistro", "fecha_de_publicacion_del",
})

_TRUE = {"si", "sí", "true", "1", "yes"}
_FALSE = {"no", "false", "0"}
_TS_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def parse_money(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def parse_int(v: Any) -> int | None:
    money = parse_money(v)
    if money is None or money != money:  # NaN
        return None
    return int(money)


def parse_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    text = str(v).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def parse_timestamp(v: Any) -> datetime | None:
    if v is None:
        return None
    text = str(v).strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _column(values: list[Any], name: str) -> pa.Array:
    if name in MONEY_COLUMNS:
        return pa.array([parse_money(v) for v in values], type=pa.float64())
    if name in INT_COLUMNS:
        return pa.array([parse_int(v) for v in values], type=pa.int64())
    if name in BOOL_COLUMNS:
        return pa.array([parse_bool(v) for v in values], type=pa.bool_())
    if name in TIMESTAMP_COLUMNS:
        return pa.array([parse_timestamp(v) for v in values], type=pa.timestamp("ms"))
    return pa.array([None if v is None else str(v) for v in values], type=pa.string())


def to_arrow(rows: list[dict[str, Any]], columns: Sequence[str]) -> pa.Table:
    return pa.table({name: _column([row.get(name) for row in rows], name) for name in columns})
