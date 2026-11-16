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


def test_feature_frame_without_labels_matches_training_features(make_raw):
    from pandas.testing import assert_frame_equal

    from procurement_risk.audit.metrics import open_audit_db
    from procurement_risk.canonical.colombia import build_canonical
    from procurement_risk.features.build import _global_rates, feature_frame
    from procurement_risk.features.history import build_history
    from procurement_risk.features.labels import build_labels

    raw = make_raw(contracts=[contract("1"), contract("2", codigo_entidad="E2"),
                              contract("3", fecha_de_firma="2026-08-01T00:00:00",
                                       fecha_de_fin_del_contrato="2026-10-01T00:00:00")],
                   processes=[PROCESS])
    training, _ = assemble_dataset(raw, AS_OF)

    con = open_audit_db(raw)
    build_canonical(con)
    build_labels(con, AS_OF)
    rates = _global_rates(con)
    build_history(con, "buyer_id", "buyer", rates)
    build_history(con, "supplier_key", "supplier", rates)
    serving = feature_frame(con, closed_only=False)
    assert set(serving["contract_id"]) == {"1", "2", "3"}
    assert "has_value_addition" not in serving.columns
    cols = ["contract_id", *CATEGORICAL_FEATURES, *NUMERIC_FEATURES]
    got = serving[serving.contract_id.isin(training.contract_id)][cols].reset_index(drop=True)
    assert_frame_equal(got, training[cols].reset_index(drop=True), check_dtype=False)


def test_global_prior_follows_train_end(make_raw):
    # Two closed contracts for E1: one with an extension signed 2021, one without in 2022.
    raw = make_raw(contracts=[
        contract("1", fecha_de_firma="2021-01-10T00:00:00",
                 fecha_de_fin_del_contrato="2021-02-10T00:00:00", dias_adicionados="5",
                 proceso_de_compra="X1"),
        contract("2", fecha_de_firma="2022-03-10T00:00:00",
                 fecha_de_fin_del_contrato="2022-04-10T00:00:00", proceso_de_compra="X2"),
        contract("3", codigo_entidad="NEW", fecha_de_firma="2023-03-10T00:00:00",
                 fecha_de_fin_del_contrato="2023-04-10T00:00:00", proceso_de_compra="X3"),
    ])
    early, _ = assemble_dataset(raw, AS_OF, train_end=date(2022, 1, 1))
    late, _ = assemble_dataset(raw, AS_OF, train_end=date(2023, 1, 1))
    new_early = early.set_index("contract_id").loc["3", "buyer_prior_extension_rate"]
    new_late = late.set_index("contract_id").loc["3", "buyer_prior_extension_rate"]
    assert new_early == 1.0   # only contract 1 (extended) is before 2022-01-01
    assert new_late == 0.5    # contracts 1 and 2
