import shutil
import time
from datetime import date

import numpy as np
import pandas as pd
import pytest

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.build import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    assemble_dataset,
    build_dataset,
)
from procurement_risk.model.explain import top_signals
from procurement_risk.serving.bundle import export_bundle, load_bundle, make_demo_bundle
from procurement_risk.serving.labels import FEATURE_LABELS
from procurement_risk.serving.scoring import UnknownBuyerError, features_for, score

AS_OF = date(2026, 11, 14)
REQUEST_FIELDS = (
    "buyer_id", "signed_at", "planned_start_at", "procurement_method", "contract_type",
    "category_code", "funding_source", "award_value", "tender_budget", "planned_duration_days",
    "tender_published_at", "n_bidders", "n_responses", "n_invited", "n_lots",
    "supplier_is_natural_person", "supplier_is_sme", "supplier_is_group",
    "advance_payment_enabled", "extendable_clause",
)
HISTORY = ("buyer_prior_n", "buyer_prior_value_addition_rate", "buyer_prior_extension_rate",
           "supplier_prior_n", "supplier_prior_value_addition_rate",
           "supplier_prior_extension_rate")


@pytest.fixture(scope="module")
def demo_path(tmp_path_factory):
    return make_demo_bundle(tmp_path_factory.mktemp("b") / "b")


@pytest.fixture(scope="module")
def demo(demo_path):
    return load_bundle(demo_path)


def contract(cid, entity, signed, end, **kw):
    base = {"id_contrato": cid, "codigo_entidad": entity, "nombre_entidad": f"Entity {entity}",
            "departamento": "Antioquia", "ciudad": "Medellín", "orden": "Territorial",
            "sector": "Salud", "rama": "Ejecutivo", "entidad_centralizada": "Centralizada",
            "modalidad_de_contratacion": "Contratación directa",
            "tipo_de_contrato": "Prestación de servicios",
            "codigo_de_categoria_principal": "V1.80111600", "origen_de_los_recursos": "SGP",
            "fecha_de_firma": signed, "fecha_de_inicio_del_contrato": signed,
            "fecha_de_fin_del_contrato": end, "dias_adicionados": "0", "es_pyme": "No",
            "es_grupo": "No", "habilita_pago_adelantado": "No",
            "el_contrato_puede_ser_prorrogado": "Si", "tipodocproveedor": "NIT",
            "proceso_de_compra": f"P{cid}"}
    return {**base, **kw}


def process(cid, value, budget, published, bidders):
    return {"id_del_portafolio": f"P{cid}", "valor_total_adjudicacion": value,
            "precio_base": budget, "fecha_de_publicacion_del": published,
            "proveedores_unicos_con": bidders, "respuestas_al_procedimiento": bidders,
            "proveedores_invitados": "3", "numero_de_lotes": "1", "duracion": "4",
            "unidad_de_duracion": "Meses"}


def test_serving_features_match_training(make_raw, demo_path, tmp_path):
    raw = make_raw(
        contracts=[contract("1", "E1", "2020-02-01T00:00:00", "2020-06-01T00:00:00"),
                   contract("2", "E1", "2021-03-10T00:00:00", "2021-07-10T00:00:00",
                            dias_adicionados="5"),
                   contract("3", "E2", "2022-12-05T00:00:00", "2023-04-05T00:00:00",
                            es_pyme="Si")],
        processes=[process("1", "1000", "1200", "2020-01-20T00:00:00", "1"),
                   process("2", None, "5000", "2021-03-01T00:00:00", "3"),
                   process("3", "800", "800", "2022-12-01T00:00:00", None)],
    )
    training, _ = assemble_dataset(raw, AS_OF)
    dataset = tmp_path / "ds.parquet"
    build_dataset(raw, dataset, AS_OF)
    models = tmp_path / "models"
    for target in ("has_value_addition", "has_time_extension"):
        (models / target).mkdir(parents=True)
        shutil.copy(demo_path / "models" / f"{target}.joblib", models / target / "model.joblib")
        (models / target / "metrics.json").write_text("{}", encoding="utf-8")
    bundle = load_bundle(export_bundle(raw, dataset, models, tmp_path / "bundle", AS_OF))

    con = open_audit_db(raw)
    build_canonical(con)
    canonical = con.execute("SELECT * FROM canonical_contracts ORDER BY contract_id").df()
    requests = [{f: (None if pd.isna(row[f]) else row[f]) if f in row else None
                 for f in REQUEST_FIELDS} for _, row in canonical.iterrows()]
    served = features_for(bundle, requests)

    cols = [*CATEGORICAL_FEATURES, *(c for c in NUMERIC_FEATURES if c not in HISTORY)]
    expected = training.sort_values("contract_id").reset_index(drop=True)[cols]
    pd.testing.assert_frame_equal(served[cols].reset_index(drop=True), expected,
                                  check_dtype=False)
    assert (served["buyer_prior_n"].to_numpy()
            >= training.sort_values("contract_id")["buyer_prior_n"].to_numpy()).all()
    assert (served["supplier_prior_n"] == 0).all()
    assert np.allclose(served["supplier_prior_value_addition_rate"],
                       bundle.metadata["global_rates"]["has_value_addition"])


def test_unknown_buyer_raises(demo):
    with pytest.raises(UnknownBuyerError):
        score(demo, [{"buyer_id": "NOPE"}])


def test_minimal_request_scores(demo):
    out = score(demo, [{"buyer_id": "DEMO-A"}])[0]
    for target in ("value_addition", "time_extension"):
        assert 0 <= out[target]["probability"] <= 1
        assert 0 <= out[target]["percentile"] <= 100
        assert len(out[target]["top_signals"]) <= 3


def test_unseen_category_warns_and_scores(demo):
    out = score(demo, [{"buyer_id": "DEMO-A", "procurement_method": "brand new method"}])[0]
    assert any("procurement_method" in w for w in out["warnings"])
    assert 0 <= out["value_addition"]["probability"] <= 1


def test_percentile_monotonic(demo):
    reqs = [{"buyer_id": "DEMO-A", "award_value": float(v)} for v in np.linspace(1, 1e9, 40)]
    pairs = sorted((r["value_addition"]["probability"], r["value_addition"]["percentile"])
                   for r in score(demo, reqs))
    assert all(b[1] >= a[1] for a, b in zip(pairs, pairs[1:], strict=False))


def test_every_feature_has_a_label():
    assert set(FEATURE_LABELS) == {*CATEGORICAL_FEATURES, *NUMERIC_FEATURES}


def test_top_signals_vectorised_is_fast(demo):
    from procurement_risk.serving.bundle import synthetic_dataset

    df = synthetic_dataset(n=2000, seed=1)
    model = demo.models["has_value_addition"]
    start = time.perf_counter()
    signals = top_signals(model, df, k=3)
    assert time.perf_counter() - start < 1.0
    assert len(signals) == 2000
    for row in signals[:50]:
        assert all(v > 0 for _, v in row)
        assert [v for _, v in row] == sorted((v for _, v in row), reverse=True)
