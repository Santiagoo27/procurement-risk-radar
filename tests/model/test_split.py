import pandas as pd

from procurement_risk.model.split import temporal_split


def test_split_boundaries():
    dates = ["2022-12-31", "2023-01-01", "2023-06-30", "2023-07-01", "2024-12-31", "2025-01-01"]
    df = pd.DataFrame({"contract_id": list("abcdef"), "signed_at": pd.to_datetime(dates)})
    s = temporal_split(df)
    assert list(s.train.contract_id) == ["a"]
    assert list(s.valid.contract_id) == ["b", "c"]
    assert list(s.test.contract_id) == ["d", "e"]
