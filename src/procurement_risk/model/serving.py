"""MLflow pyfunc wrapper so the registry serves calibrated probabilities."""

from __future__ import annotations

import joblib
import mlflow.pyfunc
import numpy as np
import pandas as pd


class RiskModelPyfunc(mlflow.pyfunc.PythonModel):
    """Loads the pickled RiskModel (booster + calibrator + vocabulary)."""

    def load_context(self, context) -> None:
        self.model = joblib.load(context.artifacts["risk_model"])

    def predict(self, context, model_input: pd.DataFrame, params=None) -> np.ndarray:
        return self.model.predict_proba(model_input)
