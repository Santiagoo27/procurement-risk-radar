"""FastAPI service: amendment risk for public contracts at signing time.

Run: uvicorn procurement_risk.api.app:create_app --factory --port 7860
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from procurement_risk.api.schemas import BuyerOut, PredictRequest, PredictResponse
from procurement_risk.serving.bundle import load_bundle
from procurement_risk.serving.labels import FEATURE_LABELS
from procurement_risk.serving.scoring import UnknownBuyerError, score

DESCRIPTION = """
Estimates, at signing time, the probability that a Colombian public contract will later
receive a **value addition** or a **time extension**, using a LightGBM model trained on
SECOP II open data (see the [GitHub repository](https://github.com/Santiagoo27/procurement-risk-radar)).

> {disclaimer}

Notes:
- Find a buyer's `buyer_id` with `GET /buyers?q=<name>`.
- Supplier history is not used by this API (it would require supplier identifiers); every
  request is scored as a supplier with no recorded history.
- Buyer history is as of the bundle date shown in `/metadata`.
"""


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def create_app(bundle_dir: Path | str | None = None) -> FastAPI:
    bundle_dir = Path(bundle_dir or os.environ.get("BUNDLE_DIR", "serving_bundle"))
    bundle = load_bundle(bundle_dir)  # fails fast with BundleError
    meta = bundle.metadata
    buyers = bundle.buyers.copy()
    buyers["_folded"] = buyers["buyer_name"].map(_fold)

    app = FastAPI(title="Procurement Risk Radar API", version=meta["bundle_version"],
                  description=DESCRIPTION.format(disclaimer=meta["disclaimer"]))
    origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "bundle_version": meta["bundle_version"]}

    @app.get("/metadata")
    def metadata() -> dict:
        return {
            "bundle_version": meta["bundle_version"],
            "as_of": meta["as_of"],
            "metrics": meta["metrics"],
            "feature_labels": FEATURE_LABELS,
            "disclaimer": meta["disclaimer"],
        }

    @app.get("/buyers", response_model=list[BuyerOut])
    def search_buyers(q: str = Query(min_length=2, max_length=100),
                      limit: int = Query(20, ge=1, le=100)) -> list[dict]:
        hits = buyers[buyers["_folded"].str.contains(_fold(q), regex=False, na=False)]
        cols = ["buyer_id", "buyer_name", "buyer_department", "buyer_city"]
        hits = hits.sort_values("buyer_name").head(limit)[cols]
        return hits.astype(object).where(hits.notna(), None).to_dict(orient="records")

    @app.post("/predict", response_model=PredictResponse)
    def predict(request: PredictRequest) -> dict:
        contracts = [c.model_dump() for c in request.contracts]
        try:
            results = score(bundle, contracts)
        except UnknownBuyerError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"unknown buyer_id '{exc.args[0]}'; search /buyers?q=<name>",
            ) from exc
        return {"bundle_version": meta["bundle_version"], "disclaimer": meta["disclaimer"],
                "results": results}

    return app
