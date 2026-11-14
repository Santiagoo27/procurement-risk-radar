import httpx
import pytest

from procurement_risk.sources.socrata import SocrataClient, SocrataError


def make_client(responses, requests, **kwargs):
    """Client whose transport replays `responses` (callables or Response) in order."""
    it = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        nxt = next(it)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    sleeps = []
    client = SocrataClient(transport=httpx.MockTransport(handler), sleep=sleeps.append,
                           **kwargs)
    return client, sleeps


def page(*ids):
    return httpx.Response(200, json=[{":id": i, "x": f"v-{i}"} for i in ids])


def test_paginates_by_id_until_empty_page():
    requests = []
    client, _ = make_client([page("row-1", "row-2"), page("row-3"), page()], requests,
                            app_token="")
    pages = list(client.iter_pages("abcd-1234", select=["x"]))
    assert [len(p) for p in pages] == [2, 1]
    assert all(":id" not in row for p in pages for row in p)
    assert "row-2" in requests[1].url.params["$where"]
    assert ":id > 'row-2'" in requests[1].url.params["$where"]
    assert requests[0].url.params["$order"] == ":id"


def test_combines_user_where_with_keyset():
    requests = []
    client, _ = make_client([page("a"), page()], requests, app_token="")
    list(client.iter_pages("abcd-1234", select=["x"], where="fecha_de_firma >= '2021-01-01'"))
    assert requests[0].url.params["$where"] == "(fecha_de_firma >= '2021-01-01')"
    assert requests[1].url.params["$where"] == "(fecha_de_firma >= '2021-01-01') AND :id > 'a'"


def test_retries_429_then_succeeds():
    requests = []
    client, sleeps = make_client(
        [httpx.Response(429), httpx.Response(503), page("a"), page()], requests, app_token=""
    )
    pages = list(client.iter_pages("abcd-1234", select=["x"]))
    assert pages == [[{"x": "v-a"}]]
    assert len(sleeps) == 2


def test_retries_timeouts():
    requests = []
    client, sleeps = make_client(
        [httpx.ReadTimeout("slow"), page("a"), page()], requests, app_token=""
    )
    assert len(list(client.iter_pages("abcd-1234", select=["x"]))) == 1
    assert len(sleeps) == 1


def test_raises_after_max_retries():
    requests = []
    client, _ = make_client([httpx.Response(500)] * 10, requests, app_token="",
                            max_retries=3)
    with pytest.raises(SocrataError):
        list(client.iter_pages("abcd-1234", select=["x"]))
    assert len(requests) == 3


def test_sends_app_token_header():
    requests = []
    client, _ = make_client([page()], requests, app_token="tok")
    list(client.iter_pages("abcd-1234", select=["x"]))
    assert requests[0].headers["X-App-Token"] == "tok"


def test_reads_app_token_from_env(monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "envtok")
    requests = []
    client, _ = make_client([page()], requests)
    list(client.iter_pages("abcd-1234", select=["x"]))
    assert requests[0].headers["X-App-Token"] == "envtok"


def test_honours_retry_after_and_caps_wait():
    requests = []
    client, sleeps = make_client(
        [httpx.Response(429, headers={"Retry-After": "7"}),
         httpx.Response(503, headers={"Retry-After": "9999"}), page("a"), page()],
        requests, app_token="",
    )
    list(client.iter_pages("abcd-1234", select=["x"]))
    assert sleeps == [7.0, 60.0]


def test_backoff_is_capped_and_budget_is_minutes():
    requests = []
    client, sleeps = make_client([httpx.Response(500)] * 20, requests, app_token="")
    assert client.max_retries >= 10
    with pytest.raises(SocrataError):
        list(client.iter_pages("abcd-1234", select=["x"]))
    assert max(sleeps) <= 60.0
    assert sum(sleeps) >= 300.0


def test_retries_truncated_json():
    requests = []
    client, sleeps = make_client(
        [httpx.Response(200, content=b'[{"x": '), page("a"), page()], requests, app_token=""
    )
    assert len(list(client.iter_pages("abcd-1234", select=["x"]))) == 1
    assert len(sleeps) == 1
