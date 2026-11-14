# Procurement Amendment Risk — Design

Date: 2026-11-14
Status: draft, owner decisions incorporated, pending final approval
Working name: `procurement-risk-radar` (final repo name is the owner's call)

## 1. Intent and why

The goal is to demonstrate **ML in production** end to end: an automated data pipeline, a
served and versioned model, a public demo and monitoring, on a real, messy, continuously
updated public dataset, and on a problem type other than time series.

The system estimates, **at the moment a public contract is signed**, the risk that it will
later be amended (value additions and time extensions), using Colombia's open procurement
data (SECOP II). It is built on a country-agnostic schema inspired by the **Open
Contracting Data Standard (OCDS)** so a second country (Canada) can be added later.

Audience: ML engineers and technical reviewers, plus the govtech / transparency community.
Everything in the repo is in **English**.

## 2. Goals, non-goals, anti-goals

Goals
- A working, publicly reachable system: nightly data pipeline, trained and versioned model,
  prediction API, interactive web demo with a map.
- Methodological credibility a senior ML engineer would respect: a well-defined target,
  no leakage (only information known at signing time), temporal validation, honest
  baselines, calibrated probabilities, documented limitations, model card.
- Delivered in **phases that are each shippable**: the repo must look complete and
  presentable at the end of every phase, because the owner's time is open-ended.
- Runs entirely on **free hosting**.

Non-goals
- Detecting or proving corruption.
- Real-time (sub-daily) updates.
- Electricity demand or anything overlapping the owner's paper under review.
- Canada in v1 (it is phase 5).

Anti-goals (failure even if it "works")
- Accusatory framing. The product talks about **"amendment risk signals"**, never
  "corruption" or "fraud". The demo carries a clear disclaimer that scores are statistical
  estimates for analysis, not allegations.
- Naming-and-shaming. Public views aggregate by **entity, region, contract type and
  modality**. Supplier names may appear only as they appear in the public source record
  inside a single contract's detail view; no supplier rankings or "worst supplier" lists.
- Publishing personal data (see §5.4).
- Leakage-inflated metrics. A headline AUC that only holds because post-signing fields
  slipped into features would discredit the whole portfolio piece.
- A half-built, abandoned repo, or a notebook-only project.

## 3. What was verified in the data (2026-11-14)

Socrata API on datos.gov.co, no token needed for small queries (an app token is free and
raises rate limits).

| Dataset | ID | Rows | Notes |
|---|---|---|---|
| SECOP II – Contratos Electrónicos | `jbjy-vk9h` | 5,710,913 | Since 2015, updated daily |
| SECOP II – Adiciones | `cb9c-h8sn` | 8,510,689 | One row per contract modification |

`Adiciones` columns: `identificador`, `id_contrato`, `tipo`, `descripcion`,
`fecharegistro`. **It has no amount column.** Modification types (row counts):

| tipo | rows |
|---|---|
| Modificacion General | 4,140,496 |
| Conclusion | 2,061,504 |
| No definido | 1,668,876 |
| Adicion en el valor | 259,266 |
| Reactivación | 142,455 |
| Suspensión | 129,416 |
| Cesion | 108,152 |
| Extension | 380 |
| Reduccion en el valor | 143 |

- Distinct contracts with at least one `Adicion en el valor`: **201,853** (~3.5% of contracts).
- Contracts with `dias_adicionados > 0` in the contracts table: **845,478** (~15%).
- The contracts table has ~90 columns, including `valor_del_contrato`, `dias_adicionados`,
  `fecha_de_firma`, `fecha_de_inicio_del_contrato`, `fecha_de_fin_del_contrato`,
  `modalidad_de_contratacion`, `tipo_de_contrato`, `codigo_de_categoria_principal`
  (UNSPSC), `departamento`, `ciudad`, `orden`, `sector`, `objeto_del_contrato`,
  `origen_de_los_recursos`, `es_pyme`, `estado_contrato`, `ultima_actualizacion`.

Consequence: the original plan ("probability of a >30% cost overrun") is **not directly
supported**, because amendment amounts are not published in `Adiciones`, and it is not yet
known whether `valor_del_contrato` is the original or the amended value.

## 4. Target definition

Primary target (v1): **`has_value_addition`** — binary, 1 if the contract receives at least
one `Adicion en el valor` modification. Base rate ~3.5% (imbalanced; report PR-AUC, not
just ROC-AUC).

Secondary target (v1): **`has_time_extension`** — binary, 1 if `dias_adicionados > 0`
(or an `Extension` modification). Base rate ~15%.

Stretch target (only if the phase-0 audit makes it possible): severity of the value
addition as a fraction of the original value, e.g. ≥30%. Possible sources: comparing
snapshots of `valor_del_contrato` over time (the nightly pipeline will start archiving
snapshots from day one, which makes this measurable going forward), or the SECOP II
Procesos dataset's base price.

Right-censoring rule: a contract only gets a label once it is **closed** (terminated /
liquidated / end date passed plus a grace window to be set in phase 0). Open contracts are
scored but never used for training or evaluation, otherwise recent contracts look
artificially "safe".

## 5. Constraints

### 5.1 Leakage
Only information knowable at `fecha_de_firma` may be a feature. Known dangerous columns
(exclude, or reconstruct their signing-time value): `valor_del_contrato` (may already
include additions), `fecha_de_fin_del_contrato` and `duraci_n_del_contrato` (may be moved
by extensions), `dias_adicionados`, `estado_contrato`, `valor_pagado`, `valor_facturado`,
`valor_pendiente_*`, `saldo_*`, `liquidaci_n`, `ultima_actualizacion`. Historical
entity-level features (e.g. an entity's past amendment rate) must be computed **only from
contracts closed before the signing date** (point-in-time joins).

### 5.2 Validation
Temporal split by signing date (train on older, validate on newer, test on the most recent
closed contracts). No random K-fold across time. Report against baselines.

### 5.3 Free hosting
No always-on paid database or server. Scale: millions of rows, so storage is Parquet +
DuckDB, not a free-tier Postgres.

### 5.4 Personal data
The contracts table contains personal and sensitive fields: legal representative name,
ID number, gender, nationality; supervisor and payment-authoriser names and ID numbers;
**bank name, account type and account number**. These are dropped at ingestion, are never
stored in published artifacts, never used as features, and never shown in the UI.

## 6. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | **Batch + static outputs**: GitHub Actions runs a nightly pipeline, writes Parquet/JSON artifacts; React frontend on Vercel reads them; FastAPI on Hugging Face Spaces for on-demand scoring | Truly free and robust; demonstrates orchestration, validation, versioning, retraining. Data lags by one day (irrelevant for contracts) | **Chosen** by the owner |
| B | Always-on backend: FastAPI + free Postgres (Neon/Supabase) + Render cron | Looks more like a company product, but free tiers sleep, cap storage and compute; millions of rows would mean fighting infrastructure instead of doing ML | Rejected |
| C | Single Streamlit app | Fastest to a demo, but reads as "notebook", the opposite of what the project sets out to show | Rejected |

Target framing alternatives (decided earlier in the conversation):
anomaly detection without labels (not evaluable, rejected); external sanction/fiscal
responsibility labels (too sparse and hard to join, rejected); **supervised proxy on
recorded post-signing outcomes (chosen)**, with interpretable risk signals shown alongside.

## 7. Architecture (decided at the level of approach A)

```
datos.gov.co (Socrata API)
      │  nightly, incremental by ultima_actualizacion / fecharegistro
      ▼
GitHub Actions ── ingest ─► validate ─► canonical schema (OCDS-inspired) ─► features
      │                                                                       │
      │                         monthly / on demand: train ─► evaluate ─► promotion gate
      │                                                                       │
      ▼                                                                       ▼
 published artifacts (Parquet/JSON: scores, aggregates, monitoring)    model registry
      │                                                                       │
      ├──────────► React frontend (Vercel): map, entity views, contract lookup
      └──────────► FastAPI (Hugging Face Spaces, Docker): /predict with explanations
```

Decided components:
- **Pipeline orchestration:** GitHub Actions (scheduled workflows).
- **Storage/compute:** Parquet files + DuckDB.
- **Canonical schema:** OCDS-inspired (parties, tender, award, contract, amendments) so
  country adapters map into it; Colombia is the first adapter.
- **Models:** baselines first (base rate, per-entity historical rate, logistic regression),
  then gradient boosting; probability calibration; SHAP explanations.
- **Experiment tracking and model registry:** MLflow.
- **API:** FastAPI in Docker on Hugging Face Spaces.
- **Frontend:** React on Vercel (the owner already deploys there). Includes an
  **interactive map of Colombia** by department and municipality showing amendment-risk
  rates, drilling down to the contracts in an area.
- **Language:** English everywhere (code, README, UI, docs).

## 8. Phases (each one ships a presentable repo)

- **Phase 0 — Data audit (spike).** Pull a sample (e.g. contracts signed in one or two
  years), join with `Adiciones`, confirm: label coverage over time, how
  `valor_del_contrato` and end dates behave after amendments, the closed-contract
  definition and grace window, which fields are safe at signing time, and whether the
  SECOP II Procesos dataset adds bidder counts / base price. Output: a short written data
  audit in `docs/` that fixes the target and the feature whitelist. **Gate:** if the
  primary target turns out to be unusable, come back to the owner before Phase 1.
- **Phase 1 — Pipeline + model.** Incremental ingestion, PII drop, validation, canonical
  schema, point-in-time features, temporal split, baselines, gradient boosting,
  calibration, SHAP, MLflow tracking, model card, README with results and figures.
- **Phase 2 — Serving.** FastAPI `/predict` and `/health`, Docker image, tests, CI on
  every push, deployment to Hugging Face Spaces.
- **Phase 3 — Web demo.** React app on Vercel: national map, entity and region views,
  contract lookup with score and top signals, methodology page, disclaimer.
- **Phase 4 — Automation and monitoring.** Nightly scoring of new contracts, scheduled
  retraining with a promotion gate (new model only replaces the current one if it beats it
  on the latest temporal holdout), data-quality checks, drift reports published as
  artifacts, snapshot archive of `valor_del_contrato` to enable the severity target.
- **Phase 5 — Canada adapter.** Map Government of Canada "Proactive disclosure of contracts
  over $10,000" (open.canada.ca; federal only, since 2017, amendments reported when they
  change value by more than $10,000) into the canonical schema; evaluate transfer or train
  a separate model; compare countries in the README.

## 9. Left to the builder

- Final repo name and Python project layout, package manager, linting/formatting tools.
- Exact model family and hyperparameter search (within "baselines first, then GBM").
- Where MLflow runs and where large artifacts live within free tiers (e.g. self-contained
  file store committed as release assets, Hugging Face Datasets, or DagsHub); must stay free.
- Data validation library and drift tooling.
- Map library and the source of Colombia's department/municipality boundaries (must have a
  license compatible with public redistribution).
- Frontend framework details (React is decided; build tool, styling and UI kit are open).
- How much historical data to train on, bounded by GitHub Actions runner limits.
- Exact text classification of `objeto_del_contrato` (TF-IDF, embeddings, or none in v1).

## 10. Owner decisions (after builder check)

- **Natural-person suppliers stay in the data.** For suppliers whose document type is a
  personal ID (not a NIT of a company), name and ID number are replaced at ingestion by a
  salted hash (salt stored as a GitHub Actions secret, never committed). The hash is used
  only internally for supplier-history features; the UI shows "Natural person". Company
  suppliers are shown as they appear in SECOP, only in a single contract's detail view, with
  no supplier rankings.
- **Map content.** Default layer: **observed** value-addition rate on **closed** contracts,
  by department and municipality. A selector switches to the observed time-extension rate
  and to a **predicted** risk layer for open contracts, clearly labelled as an estimate.
  The pipeline publishes both observed and predicted aggregates for both targets.

## 11. Calls made by the designer (owner may override)

- **Serving contract (`/predict`).** Two paths. (a) Existing SECOP contracts: the nightly
  pipeline precomputes scores and explanations; the frontend reads them from the published
  static artifacts, so no API call is needed. (b) `/predict` takes a hypothetical contract
  described by signing-time attributes plus an entity code; the API looks up that entity's
  point-in-time history in a compact entity-stats table built by the pipeline and bundled
  into the Docker image at deploy time. This keeps the Space small and offline from the
  raw data.
- **Phase 0 fallback.** `has_value_addition` is "unusable" if the audit estimates that
  more than ~30% of real value additions are hidden under `Modificacion General` /
  `No definido` and cannot be recovered by matching keywords in `descripcion` (e.g.
  "adición", "valor"). Fallback order: (1) a text-recovered value-addition label;
  (2) promote `has_time_extension` to primary. The builder proceeds with the fallback and
  reports the change; the owner is informed, not blocked on.
- **Snapshot archive starts in Phase 1.** A minimal scheduled job stores a daily
  snapshot of `id_contrato`, `valor_del_contrato`, `fecha_de_fin_del_contrato`,
  `dias_adicionados`, `estado_contrato`, as it cannot be backfilled. Phase 4 only adds
  monitoring on top of it.

## 12. Open questions the audit must answer

1. Is `valor_del_contrato` the original or the amended value?
2. Do `fecha_de_fin_del_contrato` / `duraci_n_del_contrato` change after extensions?
3. What fraction of value additions are recorded with `tipo = No definido` or
   `Modificacion General` instead of `Adicion en el valor` (label noise)?
4. What is a reliable "closed contract" definition?
5. Can number of bidders / single-bidder flag be obtained from SECOP II Procesos?
