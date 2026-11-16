import json
from datetime import date

import pytest

from procurement_risk.audit.metrics import open_audit_db
from procurement_risk.canonical.colombia import build_canonical
from procurement_risk.features.build import feature_frame
from procurement_risk.features.history import build_history
from procurement_risk.features.labels import build_labels
from procurement_risk.serving.bundle import load_bundle, make_demo_bundle
from procurement_risk.web.export import export_web_data

AS_OF = date(2026, 11, 14)
FORBIDDEN_KEYS = {"proveedor_adjudicado", "documento_proveedor", "codigo_proveedor",
                  "supplier_key", "objeto_del_contrato", "descripcion_del_proceso",
                  "descripcion"}


def topo(path):
    def mpio(code, name, dcode, dname):
        return {"type": "Polygon", "arcs": [], "properties": {
            "mpio_code": code, "mpio_name": name, "dpto_code": dcode, "dpto_name": dname}}
    data = {"type": "Topology", "arcs": [], "objects": {
        "municipalities": {"type": "GeometryCollection", "geometries": [
            mpio("05001", "Medellín", "05", "Antioquia"),
            mpio("05002", "Abejorral", "05", "Antioquia"),
            mpio("11001", "Bogotá, D.C.", "11", "Bogotá, D.C.")]},
        "departments": {"type": "GeometryCollection", "geometries": []}}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def contract(cid, entity, city, signed, end, added="0", **kw):
    depto = "Distrito Capital de Bogotá" if entity == "BOG" else "Antioquia"
    return {"id_contrato": cid, "codigo_entidad": entity, "nombre_entidad": f"Entidad {entity}",
            "departamento": depto, "ciudad": city, "fecha_de_firma": signed,
            "fecha_de_fin_del_contrato": end, "dias_adicionados": added,
            "tipo_de_contrato": "Obra", "modalidad_de_contratacion": "Licitación pública",
            "proveedor_adjudicado": "SECRETO SAS", "documento_proveedor": "900999999",
            "tipodocproveedor": "NIT", "objeto_del_contrato": "TEXTO PRIVADO JUAN PEREZ",
            "supplier_is_natural_person": False,
            "urlproceso": "{'url': 'https://community.secop.gov.co/x?id=" + cid + "'}", **kw}


@pytest.fixture
def setup(make_raw, tmp_path):
    contracts = []
    # 40 closed contracts in Medellín (E1), 10 with extensions; 5 in Abejorral (E2).
    for i in range(40):
        contracts.append(contract(f"M{i}", "E1", "Medellín", "2022-03-01T00:00:00",
                                  "2022-09-01T00:00:00", added="5" if i < 10 else "0"))
    for i in range(5):
        contracts.append(contract(f"A{i}", "E2", "Abejorral", "2022-03-01T00:00:00",
                                  "2022-09-01T00:00:00"))
    # 3 open contracts for E1 (signed 2026, ending 2027).
    for i in range(3):
        contracts.append(contract(f"O{i}", "E1", "Medellín", "2026-06-01T00:00:00",
                                  "2027-06-01T00:00:00", proceso_de_compra=f"P{i}"))
    # An open contract whose procurement process is missing must not be scored.
    contracts.append(contract("NOPROC", "E1", "Medellín", "2026-06-01T00:00:00",
                              "2027-06-01T00:00:00", proceso_de_compra="MISSING"))
    # A zero-value open contract and one with a natural-person supplier.
    contracts.append(contract("ZERO", "E1", "Medellín", "2026-06-01T00:00:00",
                              "2027-06-01T00:00:00", proceso_de_compra="PZ"))
    contracts.append(contract("PERSON", "E1", "Medellín", "2026-06-01T00:00:00",
                              "2027-06-01T00:00:00", proceso_de_compra="PP",
                              tipodocproveedor="Cédula de Ciudadanía",
                              documento_proveedor="1234567", supplier_is_natural_person=True))
    processes = [{"id_del_portafolio": f"P{i}", "valor_total_adjudicacion": "5000000",
                  "precio_base": "6000000", "proveedores_unicos_con": "2"} for i in range(3)]
    processes.append({"id_del_portafolio": "PZ", "valor_total_adjudicacion": "0",
                      "precio_base": "0"})
    processes.append({"id_del_portafolio": "PP", "valor_total_adjudicacion": "9000000",
                      "precio_base": "9000000"})
    raw = make_raw(contracts=contracts, processes=processes)
    bundle = make_demo_bundle(tmp_path / "bundle")
    out = tmp_path / "web"
    report = export_web_data([raw], bundle, topo(tmp_path / "t.json"), out, AS_OF, min_n=30)
    return raw, bundle, out, report


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_department_rate_matches_hand_count(setup):
    _, _, out, _ = setup
    dpts = {d["code"]: d for d in read(out / "departments.json")}
    assert dpts["05"]["n_closed"] == 45
    assert dpts["05"]["extension_rate"] == pytest.approx(10 / 45, abs=1e-4)
    assert read(out / "summary.json")["n_closed"] == 45


def test_rates_suppressed_below_min_n(setup):
    _, _, out, _ = setup
    mpios = {m["code"]: m for m in read(out / "municipalities.json")}
    assert mpios["05001"]["extension_rate"] == pytest.approx(10 / 40, abs=1e-4)
    assert mpios["05002"]["n_closed"] == 5
    assert mpios["05002"]["extension_rate"] is None
    entities = {e["buyer_id"]: e for e in read(out / "entities.json")}
    assert entities["E2"]["value_addition_rate"] is None


def test_open_contracts_scored_with_shared_features(setup):
    raw, bundle_dir, out, _ = setup
    bundle = load_bundle(bundle_dir)
    shard = read(out / "entities" / "antioquia.json")
    top = shard["E1"]["top_open"]
    assert {c["id_contrato"] for c in top if c["id_contrato"]} == {"O0", "O1", "O2"}

    con = open_audit_db(raw)
    build_canonical(con)
    build_labels(con, AS_OF)
    rates = bundle.metadata["global_rates"]
    build_history(con, "buyer_id", "buyer", rates)
    build_history(con, "supplier_key", "supplier", rates)
    features = feature_frame(con, closed_only=False).set_index("contract_id").loc[["O0"]]
    expected = bundle.models["has_value_addition"].predict_proba(features.reset_index())[0]
    got = next(c for c in top if c["id_contrato"] == "O0")["value_addition"]["probability"]
    assert got == pytest.approx(expected, abs=1e-4)


def test_web_data_has_no_private_fields(setup):
    _, _, out, _ = setup
    secrets = {"SECRETO SAS", "900999999", "TEXTO PRIVADO JUAN PEREZ"}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in FORBIDDEN_KEYS, key
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        else:
            assert node not in secrets, node

    files = list(out.rglob("*.json"))
    assert len(files) >= 5
    for path in files:
        walk(read(path))
        text = path.read_text(encoding="utf-8")
        assert not any(s in text for s in secrets)


def test_urlproceso_unwrapped(setup):
    _, _, out, _ = setup
    top = read(out / "entities" / "antioquia.json")["E1"]["top_open"]
    company = [c for c in top if c["id_contrato"]]
    assert company[0]["url"].startswith("https://community.secop.gov.co/x?id=O")


def test_open_audit_db_accepts_several_roots(make_raw, tmp_path):
    first = make_raw(contracts=[contract("X1", "E1", "Medellín", "2022-01-01T00:00:00",
                                         "2022-02-01T00:00:00")])
    con = open_audit_db([first, tmp_path / "missing-root"])
    assert con.execute("SELECT count(*) FROM contracts").fetchone()[0] == 1


def test_open_contracts_without_process_are_not_scored(setup):
    _, _, out, report = setup
    assert report["n_open_scored"] == 5
    top = read(out / "entities" / "antioquia.json")["E1"]["top_open"]
    assert "NOPROC" not in {c["id_contrato"] for c in top}


def test_floats_are_rounded(setup):
    _, _, out, _ = setup
    text = (out / "departments.json").read_text(encoding="utf-8")
    import re
    assert not re.search(r"\d\.\d{5,}", text)


def test_predicted_layer_flagged_unavailable_when_too_few_open_contracts(setup):
    _, _, out, _ = setup
    summary = read(out / "summary.json")
    assert summary["predicted_layer_available"] is False
    assert summary["min_open_for_predicted_layer"] == 10_000


def test_summary_lists_the_features_the_production_models_use(setup):
    from procurement_risk.serving.bundle import FEATURES

    _, _, out, _ = setup
    assert read(out / "summary.json")["model_features"] == FEATURES


def test_zero_value_contracts_are_not_listed(setup):
    _, _, out, _ = setup
    top = read(out / "entities" / "antioquia.json")["E1"]["top_open"]
    assert all(c["award_value"] for c in top)
    assert "ZERO" not in {c["id_contrato"] for c in top}


def test_natural_person_contracts_have_no_identifier(setup):
    _, _, out, _ = setup
    top = read(out / "entities" / "antioquia.json")["E1"]["top_open"]
    persons = [c for c in top if c["supplier_is_natural_person"]]
    assert len(persons) == 1
    assert persons[0]["id_contrato"] is None and persons[0]["url"] is None
    assert "PERSON" not in (out / "entities" / "antioquia.json").read_text(encoding="utf-8")


def test_refuses_to_delete_an_unrelated_directory(make_raw, tmp_path):
    raw = make_raw(contracts=[contract("X", "E1", "Medellín", "2022-03-01T00:00:00",
                                       "2022-09-01T00:00:00")])
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep me", encoding="utf-8")
    bundle = make_demo_bundle(tmp_path / "bundle")
    with pytest.raises(ValueError, match="not a web data directory"):
        export_web_data([raw], bundle, topo(tmp_path / "t.json"), victim, AS_OF)
    assert (victim / "precious.txt").exists()


def test_export_percentile_matches_api(setup):
    from procurement_risk.serving.scoring import _percentile

    _, bundle_dir, out, _ = setup
    quantiles = load_bundle(bundle_dir).metadata["score_quantiles"]["has_value_addition"]
    for c in read(out / "entities" / "antioquia.json")["E1"]["top_open"]:
        p = c["value_addition"]["probability"]
        assert c["value_addition"]["percentile"] == _percentile(quantiles, p)
