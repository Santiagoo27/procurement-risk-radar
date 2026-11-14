from datetime import date

import pyarrow.parquet as pq
import pytest

from procurement_risk import __main__ as cli
from procurement_risk.ingest import ingest_amendments, ingest_contracts

SALT = b"salt"


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def iter_pages(self, dataset_id, select, where=None):
        self.calls.append((dataset_id, tuple(select), where))
        yield from self.pages


def contract(i, doc_type, doc, name):
    return {"id_contrato": f"C{i}", "tipodocproveedor": doc_type, "documento_proveedor": doc,
            "proveedor_adjudicado": name, "valor_del_contrato": "1000",
            "fecha_de_firma": "2021-05-01T00:00:00.000", "n_mero_de_cuenta": "ACC-999"}


def read_dir(path):
    return pq.read_table(path).to_pylist()


def test_ingest_contracts_writes_scrubbed_parquet(tmp_path):
    client = FakeClient([
        [contract(1, "Cédula de Ciudadanía", "CC-12345", "JUAN PEREZ"),
         contract(2, "NIT", "900123456", "ACME SAS")],
        [contract(3, None, "CC-555", "ANA")],
    ])
    out = ingest_contracts(client, tmp_path, date(2021, 1, 1), date(2022, 1, 1), SALT)
    rows = read_dir(out)
    assert len(rows) == 3
    assert len(list(out.glob("part-*.parquet"))) == 2
    assert "n_mero_de_cuenta" not in rows[0]
    flat = repr(rows)
    for secret in ("CC-12345", "JUAN PEREZ", "CC-555", "ANA", "ACC-999"):
        assert secret not in flat
    assert "ACME SAS" in flat
    where = client.calls[0][2]
    assert "fecha_de_firma >= '2021-01-01T00:00:00'" in where
    assert "fecha_de_firma < '2022-01-01T00:00:00'" in where


def test_ingest_rerun_replaces_previous_parts(tmp_path):
    ingest_amendments(FakeClient([[{"id_contrato": "a"}], [{"id_contrato": "b"}]]), tmp_path)
    out = ingest_amendments(FakeClient([[{"id_contrato": "c"}]]), tmp_path)
    assert [r["id_contrato"] for r in read_dir(out)] == ["c"]


def test_ingest_contracts_requires_salt(monkeypatch, tmp_path):
    class NoCallClient:
        def __init__(self, *a, **k):
            pass

        def iter_pages(self, *a, **k):
            raise AssertionError("no request may be made without a salt")

    monkeypatch.delenv("PII_HASH_SALT", raising=False)
    monkeypatch.setattr(cli, "SocrataClient", NoCallClient)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ingest", "contracts", "--from", "2021-01-01", "--to", "2021-02-01",
                  "--out", str(tmp_path)])
    assert exc.value.code != 0


def test_failed_ingest_keeps_previous_data(tmp_path):
    from procurement_risk.sources.socrata import SocrataError

    ingest_amendments(FakeClient([[{"id_contrato": "old"}]]), tmp_path)

    class Failing:
        def iter_pages(self, *a, **k):
            yield [{"id_contrato": "new"}]
            raise SocrataError("boom")

    with pytest.raises(SocrataError):
        ingest_amendments(Failing(), tmp_path)
    assert [r["id_contrato"] for r in read_dir(tmp_path / "amendments")] == ["old"]
    assert not [p for p in tmp_path.iterdir() if p.name != "amendments"]
