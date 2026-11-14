import pytest
from fastapi.testclient import TestClient

from procurement_risk.api.app import create_app
from procurement_risk.serving.bundle import make_demo_bundle


@pytest.fixture(scope="module")
def bundle_dir(tmp_path_factory):
    return make_demo_bundle(tmp_path_factory.mktemp("api") / "bundle")


@pytest.fixture(scope="module")
def client(bundle_dir):
    return TestClient(create_app(bundle_dir))


def test_health_and_metadata(client):
    assert client.get("/health").json() == {"status": "ok", "bundle_version": "demo"}
    meta = client.get("/metadata").json()
    assert meta["bundle_version"] == "demo"
    assert "not allegations of wrongdoing" in meta["disclaimer"]
    assert "lightgbm" in meta["metrics"]["has_value_addition"]
    assert meta["feature_labels"]["n_bidders"] == "Number of bidders"


def test_buyers_search_is_accent_insensitive(client):
    found = client.get("/buyers", params={"q": "demo"}).json()
    assert {b["buyer_id"] for b in found} == {"DEMO-A", "DEMO-B", "DEMO-C"}
    assert [b["buyer_id"] for b in client.get("/buyers", params={"q": "ALCALDIA"}).json()] == [
        "DEMO-C"]
    assert set(found[0]) == {"buyer_id", "buyer_name", "buyer_department", "buyer_city"}


def test_buyers_limit_is_bounded(client):
    assert client.get("/buyers", params={"q": "demo", "limit": 1}).status_code == 200
    assert len(client.get("/buyers", params={"q": "demo", "limit": 1}).json()) == 1
    assert client.get("/buyers", params={"q": "demo", "limit": 500}).status_code == 422


def test_predict_minimal_request(client):
    resp = client.post("/predict", json={"contracts": [{"buyer_id": "DEMO-A"}]})
    assert resp.status_code == 200
    body = resp.json()
    assert "not allegations of wrongdoing" in body["disclaimer"]
    result = body["results"][0]
    for key in ("value_addition", "time_extension"):
        assert 0 <= result[key]["probability"] <= 1
        assert 0 <= result[key]["percentile"] <= 100


def test_predict_full_request(client):
    contract = {"buyer_id": "DEMO-B", "signed_at": "2024-03-01", "planned_start_at": "2024-03-05",
                "procurement_method": "a", "contract_type": "b", "category_code": "V1.80111600",
                "funding_source": "c", "award_value": 120000000, "tender_budget": 150000000,
                "planned_duration_days": 180, "tender_published_at": "2024-02-01",
                "n_bidders": 1, "n_responses": 1, "n_invited": 5, "n_lots": 1,
                "supplier_is_natural_person": False, "supplier_is_sme": True,
                "supplier_is_group": False, "advance_payment_enabled": True,
                "extendable_clause": True}
    resp = client.post("/predict", json={"contracts": [contract, {"buyer_id": "DEMO-C"}]})
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


def test_predict_unknown_buyer_404(client):
    resp = client.post("/predict", json={"contracts": [{"buyer_id": "NOPE"}]})
    assert resp.status_code == 404
    assert "/buyers" in resp.json()["detail"]


def test_predict_unseen_category_warns(client):
    resp = client.post("/predict", json={"contracts": [
        {"buyer_id": "DEMO-A", "procurement_method": "brand new"}]})
    assert resp.status_code == 200
    assert any("procurement_method" in w for w in resp.json()["results"][0]["warnings"])


@pytest.mark.parametrize("bad", [
    {"award_value": -1},
    {"planned_duration_days": 4000},
    {"planned_duration_days": 0},
    {"signed_at": "1999-12-31"},
    {"category_code": "80111600"},
    {"n_bidders": -2},
])
def test_predict_rejects_out_of_range(client, bad):
    resp = client.post("/predict", json={"contracts": [{"buyer_id": "DEMO-A", **bad}]})
    assert resp.status_code == 422


def test_predict_rejects_large_batches(client):
    contracts = [{"buyer_id": "DEMO-A"}] * 51
    assert client.post("/predict", json={"contracts": contracts}).status_code == 422
    assert client.post("/predict", json={"contracts": []}).status_code == 422


def test_cors_origins_from_env(bundle_dir, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://demo.example")
    c = TestClient(create_app(bundle_dir))
    ok = c.options("/health", headers={"Origin": "https://demo.example",
                                       "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://demo.example"
    bad = c.options("/health", headers={"Origin": "https://evil.example",
                                        "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_missing_bundle_fails_fast(tmp_path):
    from procurement_risk.serving.bundle import BundleError

    with pytest.raises(BundleError):
        create_app(tmp_path / "nope")


@pytest.mark.parametrize("raw_body", [
    '{"contracts":[{"buyer_id":"DEMO-A","award_value":NaN}]}',
    '{"contracts":[{"buyer_id":"DEMO-A","award_value":Infinity}]}',
    '{"contracts":[{"buyer_id":"DEMO-A","planned_duration_days":Infinity}]}',
    '{"contracts":[{"buyer_id":"DEMO-A","tender_budget":-Infinity}]}',
])
def test_predict_rejects_nan_and_infinity(client, raw_body):
    resp = client.post("/predict", content=raw_body,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    resp.json()  # the error body itself must be valid JSON


@pytest.mark.parametrize("bad", [{"n_bidders": 10**30}, {"n_lots": 100_001},
                                 {"award_value": 1e20}, {"tender_budget": 1e20},
                                 {"signed_at": "2999-01-01"}])
def test_predict_rejects_huge_values(client, bad):
    resp = client.post("/predict", json={"contracts": [{"buyer_id": "DEMO-A", **bad}]})
    assert resp.status_code == 422


def test_buyers_search_matches_words_in_any_order(client):
    found = client.get("/buyers", params={"q": "demo  alcaldia"}).json()
    assert [b["buyer_id"] for b in found] == ["DEMO-C"]


def test_minimal_request_warns_about_signing_date(client):
    resp = client.post("/predict", json={"contracts": [{"buyer_id": "DEMO-A"}]})
    assert any("signed_at" in w for w in resp.json()["results"][0]["warnings"])
