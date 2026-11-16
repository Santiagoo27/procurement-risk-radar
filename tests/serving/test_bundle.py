import json
import shutil
from datetime import date

import numpy as np
import pandas as pd
import pytest

from procurement_risk.features.build import build_dataset
from procurement_risk.serving.bundle import (
    BUYER_COLUMNS,
    BundleError,
    export_bundle,
    load_bundle,
    make_demo_bundle,
)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return make_demo_bundle(tmp_path_factory.mktemp("bundle") / "b")


def test_demo_bundle_roundtrip(demo):
    bundle = load_bundle(demo)
    assert set(bundle.models) == {"has_value_addition", "has_time_extension"}
    assert len(bundle.buyers) == 3
    for target in bundle.models:
        q = bundle.metadata["score_quantiles"][target]
        assert len(q) == 101
        assert np.all(np.diff(q) >= 0)


def test_bundle_accepts_subset_and_rejects_unknown_features(demo, tmp_path):
    meta = json.loads((demo / "metadata.json").read_text(encoding="utf-8"))
    older = tmp_path / "older"
    shutil.copytree(demo, older)
    (older / "metadata.json").write_text(
        json.dumps({**meta, "features": meta["features"][:-1]}), encoding="utf-8")
    load_bundle(older)  # a bundle trained with fewer features still loads

    newer = tmp_path / "newer"
    shutil.copytree(demo, newer)
    (newer / "metadata.json").write_text(
        json.dumps({**meta, "features": [*meta["features"], "made_up"]}), encoding="utf-8")
    with pytest.raises(BundleError, match="made_up"):
        load_bundle(newer)

def test_bundle_rejects_missing_model(demo, tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(demo, broken)
    (broken / "models" / "has_time_extension.joblib").unlink()
    with pytest.raises(BundleError, match="has_time_extension"):
        load_bundle(broken)


def test_bundle_contains_no_supplier_columns(demo):
    assert list(pd.read_parquet(demo / "buyers.parquet").columns) == list(BUYER_COLUMNS)
    for path in demo.rglob("*"):
        if path.suffix in {".json", ".parquet"}:
            blob = path.read_bytes()
            for word in (b"supplier_key", b"documento_proveedor", b"proveedor_adjudicado"):
                assert word not in blob, (path, word)


def contract(cid, entity, signed, end):
    return {"id_contrato": cid, "codigo_entidad": entity, "nombre_entidad": f"Entity {entity}",
            "departamento": "Antioquia", "fecha_de_firma": signed,
            "fecha_de_fin_del_contrato": end, "dias_adicionados": "0"}


def test_export_bundle_buyer_history_as_of(make_raw, demo, tmp_path):
    as_of = date(2026, 11, 14)
    raw = make_raw(contracts=[
        contract("1", "E1", "2019-01-01T00:00:00", "2019-06-01T00:00:00"),
        contract("2", "E1", "2020-01-01T00:00:00", "2020-06-01T00:00:00"),
        contract("3", "E1", "2026-06-01T00:00:00", "2026-10-01T00:00:00"),
        contract("4", "E2", "2021-01-01T00:00:00", "2021-06-01T00:00:00"),
    ])
    dataset = tmp_path / "ds.parquet"
    build_dataset(raw, dataset, as_of)
    models = tmp_path / "models"
    for target in ("has_value_addition", "has_time_extension"):
        (models / target).mkdir(parents=True)
        shutil.copy(demo / "models" / f"{target}.joblib", models / target / "model.joblib")
        (models / target / "metrics.json").write_text("{}", encoding="utf-8")
    out = export_bundle(raw, dataset, models, tmp_path / "bundle", as_of)
    buyers = load_bundle(out).buyers.set_index("buyer_id")
    assert buyers.loc["E1", "buyer_prior_n"] == 2
    assert buyers.loc["E2", "buyer_prior_n"] == 1
    assert buyers.loc["E1", "buyer_name"] == "Entity E1"
    assert load_bundle(out).metadata["as_of"] == "2026-11-14"


def test_demo_bundle_cli(tmp_path):
    from procurement_risk import __main__ as cli

    cli.main(["demo-bundle", "--out", str(tmp_path / "b")])
    assert load_bundle(tmp_path / "b").metadata["bundle_version"] == "demo"



def test_export_uses_training_global_rates(make_raw, demo, tmp_path):
    raw = make_raw(contracts=[
        contract("1", "E1", "2019-01-01T00:00:00", "2019-06-01T00:00:00"),
        contract("2", "E1", "2020-01-01T00:00:00", "2020-06-01T00:00:00"),
        # open at the training as-of, closed (with an extension) at the later export as-of
        {**contract("3", "E1", "2022-06-01T00:00:00", "2026-10-01T00:00:00"),
         "dias_adicionados": "30"},
    ])
    dataset = tmp_path / "ds.parquet"
    build_dataset(raw, dataset, date(2026, 11, 14))
    models = tmp_path / "models"
    for target in ("has_value_addition", "has_time_extension"):
        (models / target).mkdir(parents=True)
        shutil.copy(demo / "models" / f"{target}.joblib", models / target / "model.joblib")
        (models / target / "metrics.json").write_text("{}", encoding="utf-8")
    out = export_bundle(raw, dataset, models, tmp_path / "bundle", date(2027, 6, 1))
    rates = load_bundle(out).metadata["global_rates"]
    assert rates["has_time_extension"] == 0.0  # training rows (1, 2) had no extension


def test_bundle_records_library_versions_and_rejects_mismatch(demo, tmp_path):
    meta = json.loads((demo / "metadata.json").read_text(encoding="utf-8"))
    assert {"lightgbm", "scikit-learn"} <= set(meta["library_versions"])
    broken = tmp_path / "broken"
    shutil.copytree(demo, broken)
    meta["library_versions"]["lightgbm"] = "0.0.1"
    (broken / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(BundleError, match="lightgbm"):
        load_bundle(broken)


def test_bundle_records_training_window(demo):
    meta = json.loads((demo / "metadata.json").read_text(encoding="utf-8"))
    assert meta["train_end"] == "2023-01-01"
    assert meta["data_end"] == "2025-01-01"


def test_export_records_where_each_model_came_from(make_raw, demo, tmp_path):
    raw = make_raw(contracts=[
        contract("1", "E1", "2019-01-01T00:00:00", "2019-06-01T00:00:00"),
        contract("2", "E1", "2024-01-01T00:00:00", "2024-06-01T00:00:00"),
    ])
    dataset = tmp_path / "ds.parquet"
    build_dataset(raw, dataset, date(2026, 11, 14))
    models = tmp_path / "models"
    sources = {
        "has_value_addition": {"source": "retrained", "train_end": "2023-11-16",
                               "data_end": "2025-11-16"},
        "has_time_extension": {"source": "kept", "bundle_version": "model-2026-11-14",
                               "train_end": "2023-01-01", "data_end": "2025-01-01"},
    }
    for target, source in sources.items():
        (models / target).mkdir(parents=True)
        shutil.copy(demo / "models" / f"{target}.joblib", models / target / "model.joblib")
        (models / target / "metrics.json").write_text("{}", encoding="utf-8")
        (models / target / "source.json").write_text(json.dumps(source), encoding="utf-8")
    dates = (date(2023, 11, 16), date(2024, 5, 16), date(2025, 11, 16))
    meta = load_bundle(export_bundle(raw, dataset, models, tmp_path / "bundle",
                                     date(2026, 11, 16), dates)).metadata
    assert meta["model_sources"] == sources
    assert meta["train_end"] == "2023-11-16"
    # realized performance must use contracts that no model in the bundle has seen
    assert meta["data_end"] == "2025-11-16"
