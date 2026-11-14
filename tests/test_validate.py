import pandas as pd
import pytest

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from procurement_risk.validate import DatasetValidationError, validate_dataset


def good(n=200):
    data = {"contract_id": [str(i) for i in range(n)],
            "signed_at": pd.to_datetime(["2021-01-01"] * n)}
    for col in CATEGORICAL_FEATURES:
        data[col] = ["a"] * n
    for col in NUMERIC_FEATURES:
        data[col] = [1.0] * n
    data["has_value_addition"] = [i % 10 == 0 for i in range(n)]
    data["has_time_extension"] = [i % 5 == 0 for i in range(n)]
    return pd.DataFrame(data)


def test_valid_dataset_passes():
    validate_dataset(good())


def test_validate_rejects_duplicates():
    df = good()
    df.loc[1, "contract_id"] = df.loc[0, "contract_id"]
    with pytest.raises(DatasetValidationError, match="duplicate"):
        validate_dataset(df)


def test_validate_rejects_all_null_feature():
    df = good()
    df["n_bidders"] = None
    with pytest.raises(DatasetValidationError, match="n_bidders"):
        validate_dataset(df)


def test_validate_rejects_implausible_rate():
    df = good()
    df["has_value_addition"] = True
    with pytest.raises(DatasetValidationError, match="has_value_addition"):
        validate_dataset(df)


def test_validate_rejects_forbidden_column():
    df = good()
    df["valor_del_contrato"] = 1.0
    with pytest.raises(DatasetValidationError, match="valor_del_contrato"):
        validate_dataset(df)


def test_cli_does_not_write_invalid_dataset(make_raw, tmp_path):
    from procurement_risk import __main__ as cli

    raw = make_raw(contracts=[{"id_contrato": "1", "fecha_de_firma": "2021-03-10T00:00:00",
                               "fecha_de_fin_del_contrato": "2021-12-31T00:00:00"}])
    out = tmp_path / "ds.parquet"
    with pytest.raises(SystemExit) as exc:
        cli.main(["build-dataset", "--raw", str(raw), "--out", str(out),
                  "--as-of", "2026-11-14"])
    assert exc.value.code == 3
    assert not out.exists()
