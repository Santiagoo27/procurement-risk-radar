import numpy as np
import pandas as pd
import pytest

from procurement_risk.features.build import CATEGORICAL_FEATURES, NUMERIC_FEATURES


@pytest.fixture
def synthetic():
    """2,000 rows over 2021-2024; has_value_addition driven by log_award_value."""
    rng = np.random.default_rng(0)
    n = 2000
    df = pd.DataFrame({
        "contract_id": [str(i) for i in range(n)],
        "signed_at": pd.to_datetime("2021-01-01")
        + pd.to_timedelta(rng.integers(0, 4 * 365, n), unit="D"),
        "buyer_id": rng.choice(["E1", "E2", "E3"], n),
    })
    for col in CATEGORICAL_FEATURES:
        df[col] = rng.choice(["a", "b", "c"], n)
    for col in NUMERIC_FEATURES:
        df[col] = rng.normal(size=n)
    logit = 2.5 * df["log_award_value"] - 2.0
    df["has_value_addition"] = rng.random(n) < 1 / (1 + np.exp(-logit))
    df["has_time_extension"] = rng.random(n) < 0.2
    return df
