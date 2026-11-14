import pytest

from procurement_risk import config
from procurement_risk.privacy import (
    MissingSaltError,
    hash_identifier,
    is_natural_person,
    load_salt,
    project,
    scrub_contract,
)

SALT = b"test-salt"


@pytest.mark.parametrize("doc_type", ["NIT", " nit ", "Nit"])
def test_nit_is_company(doc_type):
    assert is_natural_person(doc_type) is False


@pytest.mark.parametrize(
    "doc_type", [None, "", "Cédula de Ciudadanía", "Pasaporte", "NIT..", "Otro", "No Definido"]
)
def test_unknown_or_empty_doc_type_is_natural_person(doc_type):
    assert is_natural_person(doc_type) is True


def test_scrub_hashes_natural_person():
    row = {
        "id_contrato": "CO1.PCCNTR.1",
        "tipodocproveedor": "Cédula de Ciudadanía",
        "documento_proveedor": "12345",
        "codigo_proveedor": "777",
        "proveedor_adjudicado": "JUAN PEREZ",
        "n_mero_de_cuenta": "999",
        "nombre_supervisor": "MARIA",
    }
    out = scrub_contract(row, SALT)
    assert "n_mero_de_cuenta" not in out
    assert "nombre_supervisor" not in out
    assert out["proveedor_adjudicado"] is None
    assert out["documento_proveedor"].startswith("np_")
    assert out["codigo_proveedor"].startswith("np_")
    values = [str(v) for v in out.values()]
    assert not any("12345" in v or "JUAN PEREZ" in v or "777" == v for v in values)
    assert out["supplier_is_natural_person"] is True


def test_scrub_keeps_company_supplier():
    row = {"tipodocproveedor": "NIT", "documento_proveedor": "900123",
           "proveedor_adjudicado": "ACME SAS", "codigo_proveedor": "55"}
    out = scrub_contract(row, SALT)
    assert out["documento_proveedor"] == "900123"
    assert out["proveedor_adjudicado"] == "ACME SAS"
    assert out["codigo_proveedor"] == "55"
    assert out["supplier_is_natural_person"] is False


def test_scrub_output_columns_are_allowlist_plus_flag():
    out = scrub_contract({"extra": "x"}, SALT)
    assert set(out) == set(config.CONTRACT_COLUMNS) | {"supplier_is_natural_person"}


def test_hash_is_stable_and_salted():
    assert hash_identifier("12345", SALT) == hash_identifier(" 12345 ", SALT)
    assert hash_identifier("12345", SALT) != hash_identifier("12345", b"other")
    assert hash_identifier("", SALT) is None
    assert hash_identifier(None, SALT) is None


@pytest.mark.parametrize("env", [{}, {"PII_HASH_SALT": "  "}])
def test_missing_salt_raises(env):
    with pytest.raises(MissingSaltError):
        load_salt(env)


def test_load_salt_returns_bytes():
    assert load_salt({"PII_HASH_SALT": "abc"}) == b"abc"


def test_project_keeps_only_listed_columns():
    assert project({"a": "1", "b": "2"}, ["a", "c"]) == {"a": "1", "c": None}
