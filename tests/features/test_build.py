from datetime import date

import pandas as pd

from procurement_risk.features.build import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGETS,
    assemble_dataset,
    build_dataset,
)

AS_OF = date(2026, 11, 14)


def contract(cid, **kw):
    base = {"id_contrato": cid, "fecha_de_firma": "2021-03-10T00:00:00",
            "fecha_de_fin_del_contrato": "2021-12-31T00:00:00", "codigo_entidad": "E1",
            "proceso_de_compra": "P1", "dias_adicionados": "0"}
    return {**base, **kw}


PROCESS = {"id_del_portafolio": "P1", "valor_total_adjudicacion": "1000", "precio_base": "2000",
           "fecha_de_publicacion_del": "2021-03-01T00:00:00", "proveedores_unicos_con": "1",
           "duracion": "2", "unidad_de_duracion": "Meses"}


def test_features_are_derived(make_raw):
    df, _ = assemble_dataset(make_raw(contracts=[contract("1")], processes=[PROCESS]), AS_OF)
    row = df.iloc[0]
    assert row["days_publication_to_signing"] == 9
    assert row["award_to_budget_ratio"] == 0.5
    assert row["single_bidder"] == 1
    assert row["planned_duration_days"] == 60
    assert row["signing_month"] == 3
    assert set(CATEGORICAL_FEATURES + NUMERIC_FEATURES + TARGETS) <= set(df.columns)


def test_negative_publication_gap_is_null(make_raw):
    late = {**PROCESS, "fecha_de_publicacion_del": "2021-04-01T00:00:00"}
    df, _ = assemble_dataset(make_raw(contracts=[contract("1")], processes=[late]), AS_OF)
    assert pd.isna(df.iloc[0]["days_publication_to_signing"])


def test_rows_without_process_are_kept_and_counted(make_raw):
    raw = make_raw(contracts=[contract("1"), contract("2", proceso_de_compra="NOPE")],
                   processes=[PROCESS])
    df, summary = assemble_dataset(raw, AS_OF)
    assert summary.n_rows == 2
    assert summary.n_without_process == 1
    assert pd.isna(df.set_index("contract_id").loc["2", "log_award_value"])


def test_only_closed_contracts_in_dataset(make_raw):
    raw = make_raw(contracts=[contract("1"),
                              contract("2", fecha_de_firma="2026-08-01T00:00:00",
                                       fecha_de_fin_del_contrato="2026-10-01T00:00:00")],
                   processes=[PROCESS])
    df, _ = assemble_dataset(raw, AS_OF)
    assert list(df["contract_id"]) == ["1"]


def test_dataset_has_no_forbidden_columns(make_raw, tmp_path):
    out = tmp_path / "ds.parquet"
    summary = build_dataset(make_raw(contracts=[contract("1")], processes=[PROCESS]), out, AS_OF)
    cols = set(pd.read_parquet(out).columns)
    assert {"valor_del_contrato", "current_end_at", "added_days", "estado_contrato",
            "supplier_key"}.isdisjoint(cols)
    assert summary.positive_rate.keys() == set(TARGETS)
