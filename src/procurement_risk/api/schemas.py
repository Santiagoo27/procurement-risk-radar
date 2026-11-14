"""Request and response models for the prediction API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 1, 1)
MAX_MONEY = 1e15  # COP; the largest SECOP contracts are around 1e13
MAX_COUNT = 100_000


class ContractIn(BaseModel):
    """Signing-time attributes of a contract. Only buyer_id is required."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, json_schema_extra={"example": {
        "buyer_id": "704010122",
        "signed_at": "2024-03-01",
        "procurement_method": "Contratación directa",
        "contract_type": "Prestación de servicios",
        "category_code": "V1.80111600",
        "award_value": 45000000,
        "planned_duration_days": 300,
        "supplier_is_natural_person": True,
    }})

    buyer_id: str = Field(min_length=1, max_length=64,
                          description="SECOP entity code; search it with GET /buyers.")
    signed_at: date | None = Field(None, ge=MIN_DATE, le=MAX_DATE,
                                    description="Defaults to today (with a warning).")
    planned_start_at: date | None = Field(None, ge=MIN_DATE, le=MAX_DATE)
    tender_published_at: date | None = Field(None, ge=MIN_DATE, le=MAX_DATE)
    procurement_method: str | None = Field(None, max_length=200)
    contract_type: str | None = Field(None, max_length=200)
    category_code: str | None = Field(None, pattern=r"^V1\.\d{8}$",
                                      description="UNSPSC code as in SECOP, e.g. V1.80111600.")
    funding_source: str | None = Field(None, max_length=200)
    award_value: float | None = Field(None, ge=0, le=MAX_MONEY,
                                      description="Awarded value in COP.")
    tender_budget: float | None = Field(None, ge=0, le=MAX_MONEY,
                                        description="Tender budget in COP.")
    planned_duration_days: float | None = Field(None, gt=0, le=3650)
    n_bidders: int | None = Field(None, ge=0, le=MAX_COUNT)
    n_responses: int | None = Field(None, ge=0, le=MAX_COUNT)
    n_invited: int | None = Field(None, ge=0, le=MAX_COUNT)
    n_lots: int | None = Field(None, ge=0, le=MAX_COUNT)
    supplier_is_natural_person: bool | None = None
    supplier_is_sme: bool | None = None
    supplier_is_group: bool | None = None
    advance_payment_enabled: bool | None = None
    extendable_clause: bool | None = None


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contracts: list[ContractIn] = Field(min_length=1, max_length=50)


class Signal(BaseModel):
    feature: str
    label: str
    provided: bool = Field(description="False when the request did not include this input; "
                                       "the model then uses its default for missing values.")
    contribution: float = Field(description="SHAP contribution to the log-odds of the risk.")


class TargetScore(BaseModel):
    probability: float = Field(description="Calibrated probability.")
    percentile: float = Field(
        description="Approximate share (0-100) of reference contracts (the model's test "
                    "period) whose calibrated score is at or below this one.")
    top_signals: list[Signal]


class ContractScore(BaseModel):
    value_addition: TargetScore
    time_extension: TargetScore
    warnings: list[str]


class PredictResponse(BaseModel):
    bundle_version: str
    disclaimer: str
    results: list[ContractScore]


class BuyerOut(BaseModel):
    buyer_id: str
    buyer_name: str | None
    buyer_department: str | None
    buyer_city: str | None
