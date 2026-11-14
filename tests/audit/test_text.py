import pytest

from procurement_risk.audit.text import looks_like_value_addition


@pytest.mark.parametrize("text", [
    "ADICIÓN EN VALOR AL CONTRATO",
    "adicionar $5.000.000 al contrato",
    "Mayor valor del contrato",
    "Adición presupuestal No. 1",
])
def test_value_additions_match(text):
    assert looks_like_value_addition(text) is True


@pytest.mark.parametrize("text", [
    "Prórroga en plazo", "ACTA DE LIQUIDACION", "Sin Descripción", None, "",
    "Adición en plazo de 30 días", "Modificación",
])
def test_non_value_additions_do_not_match(text):
    assert looks_like_value_addition(text) is False
