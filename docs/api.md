# Prediction API

A FastAPI service that estimates, at signing time, the probability that a Colombian public
contract will later receive a **value addition** or a **time extension**.

> Scores are statistical estimates for analysis, not allegations of wrongdoing.

Interactive documentation (OpenAPI) is served at [/docs](https://procurement-risk-radar-9p25.onrender.com/docs). The public instance runs on
Render's free plan and sleeps after 15 idle minutes, so the first request can take about a
minute.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check and bundle version |
| GET | `/metadata` | Bundle date, test-set metrics, feature names, disclaimer |
| GET | `/buyers?q=<words>&limit=20` | Find a buyer's `buyer_id`. Every word must appear in the name; matching ignores accents, case and order |
| POST | `/predict` | Score 1 to 50 contracts |

## Request

Only `buyer_id` is required. Every other field is optional; a missing field is treated the
way the model treats missing data during training.

| Field | Type | Meaning |
|---|---|---|
| `buyer_id` | string | SECOP entity code (`codigo_entidad`); look it up with `/buyers` |
| `signed_at` | date | Signing date. Defaults to today, with a warning |
| `planned_start_at` | date | Planned start of execution |
| `tender_published_at` | date | Publication date of the tender |
| `procurement_method` | string | SECOP modality, e.g. `Contratación directa` |
| `contract_type` | string | e.g. `Prestación de servicios`, `Obra` |
| `category_code` | string | UNSPSC code as in SECOP, e.g. `V1.80111600` |
| `funding_source` | string | e.g. `Recursos propios` |
| `award_value`, `tender_budget` | number | COP, from 0 to 1e15 |
| `planned_duration_days` | number | Greater than 0 and at most 3650 |
| `n_bidders`, `n_responses`, `n_invited`, `n_lots` | integer | From 0 to 100,000 |
| `supplier_is_natural_person`, `supplier_is_sme`, `supplier_is_group`, `advance_payment_enabled`, `extendable_clause` | boolean | Contract and supplier flags |

Dates must fall between 2000-01-01 and 2100-01-01. Out-of-range values, `NaN`, `Infinity` and
unknown fields are rejected with HTTP 422. An unknown `buyer_id` returns 404.

## Response

For each contract, both `value_addition` and `time_extension` include:

- `probability`: the calibrated probability.
- `percentile`: the approximate share (0–100) of contracts in the model's test period
  (signed July 2023 to December 2024) whose score is at or below this one.
- `top_signals`: up to three features that raise the risk the most. Each has a readable
  `label`, a `contribution` (SHAP, in log-odds) and `provided`. `provided` is false when
  the request did not include that input, and the label then ends in "(not provided)".

`warnings` lists category values the model has not seen and dates that were filled in
for you.

## Example

```bash
curl -s https://procurement-risk-radar-9p25.onrender.com/buyers?q=medellin%20distrito
```

```bash
curl -s -X POST https://procurement-risk-radar-9p25.onrender.com/predict -H "Content-Type: application/json" -d '{"contracts":[{"buyer_id":"700221021","signed_at":"2025-01-15","procurement_method":"Contratación directa","contract_type":"Prestación de servicios","award_value":40000000,"planned_duration_days":330,"supplier_is_natural_person":true}]}'
```

## How scores are computed

- Features are computed with the **same SQL** that built the training dataset, and a test
  checks the two match.
- **Buyer history** (past contracts, value-addition and extension rates) is taken as of
  the bundle date shown in `/metadata`.
- **Supplier history is not used.** Using it would require exposing supplier
  identifiers, and most suppliers are natural persons. Every request is scored as a
  supplier with no recorded history, which is how the model saw most training contracts.

## Limitations

See the [model card](model-card.md). In short:

- Value-addition labels are partly recovered from amendment text, with about 84% precision.
- The model predicts *whether* a contract is amended, not by how much.
- A high score reflects patterns of similar past contracts, not evidence about a specific
  contract.

## Running locally

```bash
uv sync --all-extras
uv run python -m procurement_risk demo-bundle --out serving_bundle   # or export-bundle
uv run uvicorn procurement_risk.api.app:create_app --factory --port 7860
```
