# Phase 1: Features and Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the raw SECOP II Parquet files into a leakage-safe training set and train, calibrate, explain and document models that estimate, at signing time, the probability that a contract will receive a value addition (primary) or a time extension (secondary).

**Architecture:** A Colombia adapter maps raw tables into an OCDS-inspired canonical schema in DuckDB. Labels follow the Phase 0 audit decisions. Point-in-time entity and supplier history features come from DuckDB ASOF joins over "label became observable" events. A temporal split feeds three baselines and a LightGBM model with isotonic calibration fitted on the validation period only. MLflow (local SQLite) tracks runs and registers the model. LightGBM's built-in SHAP contributions explain predictions. Figures and a model card are generated into `docs/`.

**Tech Stack:** Python ≥3.12, DuckDB, pyarrow, pandas, scikit-learn, LightGBM, MLflow, matplotlib, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-14-procurement-risk-design.md` (§4 targets, §5.1 leakage, §5.2 validation, §8 Phase 1). **Binding data decisions:** `docs/data-audit.md`.

## Global Constraints

- English everywhere. Outputs are "amendment risk signals"; never "corruption" or "fraud".
- **Only signing-time information is a feature** (spec §5.1). Excluded columns (audit whitelist): `valor_del_contrato`, `fecha_de_fin_del_contrato`, `duraci_n_del_contrato`, `dias_adicionados`, `estado_contrato`, `valor_facturado`, `valor_pagado`, `liquidaci_n`, `ultima_actualizacion`, identifiers, supplier names. Original value = `processes.valor_total_adjudicacion`, falling back to `processes.precio_base`.
- **Primary target `has_value_addition`:** contract has an amendment with `tipo = 'Adicion en el valor'`, OR an amendment with `tipo IN ('Modificacion General', 'No definido')` whose `descripcion` satisfies `looks_like_value_addition` (audit: hidden share 70.8%, precision 84%).
- **Secondary target `has_time_extension`:** `dias_adicionados > 0`.
- **Closed contract:** `fecha_de_fin_del_contrato <= as_of - 180 days`. `estado_contrato` is never used. Only closed contracts are labelled, trained on or evaluated. Default `as_of = 2026-11-14`.
- **Temporal split by `signed_at`:** train `< 2023-01-01`; validation `[2023-01-01, 2023-07-01)`; test `[2023-07-01, 2025-01-01)`. No random splits.
- Calibration is fitted on the **validation** split only; the test split is touched once, for final metrics.
- Primary metric PR-AUC (imbalanced); also ROC-AUC, Brier score, log loss, precision and recall in the top 5% of scores.
- Supplier names and natural-person identities never appear in any committed file, figure or log. Committed figures show aggregates only.
- Large artifacts (`data/`, `mlruns/`, `mlflow.db`) are git-ignored.

## Review Focus

1. A contract whose own label, or a label that only becomes observable later, leaks into its entity/supplier history (same day, same entity, the contract itself). Expect: history counts only events with `observable_at < signed_at`. Test in Task 3.
2. A contract with no matching process row (audit: 0.1%): award value, bidders and planned duration are null and the row is kept and counted, not silently dropped. Test in Task 4.
3. Unknown duration units, zero or negative durations, publication after signing: the derived feature is null, never a crash or a negative value. Test in Task 4.
4. Calibration accidentally fitted on test data or on training data. Expect: the calibrator only ever sees validation rows. Test in Task 6.
5. Duplicate `contract_id` rows (Socrata re-publishing) inflating a split: validation fails loudly. Test in Task 4.

---

## File Structure

```
src/procurement_risk/canonical/__init__.py
src/procurement_risk/canonical/colombia.py   # raw SECOP -> canonical tables (DuckDB)
src/procurement_risk/features/__init__.py
src/procurement_risk/features/labels.py      # targets + closure
src/procurement_risk/features/history.py     # point-in-time entity/supplier history
src/procurement_risk/features/build.py       # feature assembly, dataset parquet
src/procurement_risk/validate.py             # dataset checks
src/procurement_risk/model/__init__.py
src/procurement_risk/model/split.py          # temporal split
src/procurement_risk/model/metrics.py        # evaluation metrics
src/procurement_risk/model/baselines.py      # base rate, entity rate, logistic regression
src/procurement_risk/model/train.py          # LightGBM + calibration + MLflow
src/procurement_risk/model/explain.py        # SHAP contributions, top signals
src/procurement_risk/model/report.py         # figures + model card
tests/canonical/, tests/features/, tests/model/, tests/test_validate.py
docs/figures/*.png                            # generated, committed
docs/model-card.md                            # generated, committed
```

---

### Task 1: Canonical schema (Colombia adapter)

**Files:**
- Create: `src/procurement_risk/canonical/__init__.py`, `src/procurement_risk/canonical/colombia.py`, `tests/canonical/__init__.py`, `tests/canonical/test_colombia.py`
- Modify: `pyproject.toml` (add `pandas`, `scikit-learn`, `lightgbm`, `mlflow`, `matplotlib`), `.gitignore` (add `mlruns/`, `mlflow.db`)

**Interfaces:**
- Consumes: `audit.metrics.open_audit_db(raw_dir)` (views `contracts`, `amendments`, `processes`, UDF `looks_like_value_addition`, temp table `process_one`).
- Produces: `build_canonical(con: duckdb.DuckDBPyConnection) -> None`, creating two tables:
  - `canonical_contracts`: `contract_id, tender_id, buyer_id, buyer_department, buyer_city, buyer_order, buyer_sector, buyer_branch, buyer_centralized, procurement_method, contract_type, category_code, category_segment, funding_source, signed_at, planned_start_at, current_end_at, award_value, tender_budget, planned_duration_days, tender_published_at, n_bidders, n_responses, n_invited, n_lots, supplier_key, supplier_is_natural_person, supplier_is_sme, supplier_is_group, advance_payment_enabled, extendable_clause, added_days`. `tender_id = proceso_de_compra`; `buyer_id = codigo_entidad`; `supplier_key = codigo_proveedor` (already hashed for natural persons); `award_value = valor_total_adjudicacion` (falls back to `precio_base`); `tender_budget = precio_base`; `current_end_at` and `added_days` exist **only** for labels/closure and are never features.
  - `canonical_amendments`: `amendment_id, contract_id, kind, recorded_at` with `kind ∈ {'value_addition', 'value_addition_text', 'extension', 'other'}` (`value_addition` = explicit type; `value_addition_text` = hidden type with matching text; `extension` = `tipo = 'Extension'`).
  - `category_segment` = first two digits of the UNSPSC code (`"V1.80111600"` → `"80"`); `planned_duration_days` = `processes.duracion × unit factor` with `unidad_de_duracion` normalized (accents/case removed) mapping `dia→1, semana→7, mes→30, ano→365, hora→1/24`; unknown unit or a value ≤ 0 → null.

- [ ] **Step 1: Write failing tests** (fixtures built with `parsing.to_arrow` as in `tests/audit/test_metrics.py`):
  - `test_award_value_falls_back_to_budget`: process with `valor_total_adjudicacion=None, precio_base="500"` → `award_value == 500.0`.
  - `test_missing_process_keeps_contract` (Review Focus 2): a contract with unknown `proceso_de_compra` → present in `canonical_contracts` with `award_value IS NULL`, `n_bidders IS NULL`.
  - `test_duration_units` (Review Focus 3): `("3","Meses")→90`, `("2","Semana(s)")→14`, `("1","Año")→365`, `("10","Quincenas")→None`, `("0","Dias")→None`.
  - `test_category_segment`: `"V1.80111600"→"80"`, `None→None`.
  - `test_amendment_kinds`: explicit addition → `value_addition`; `Modificacion General` with `"ADICIÓN EN VALOR"` → `value_addition_text`; `Modificacion General` with `"Prórroga"` → `other`; `Extension` → `extension`.
  - `test_no_excluded_columns_leak_as_features`: `canonical_contracts` has no column named `valor_del_contrato`, `estado_contrato`, `proveedor_adjudicado`.
- [ ] **Step 2:** `uv run pytest tests/canonical -v` → FAIL (module missing).
- [ ] **Step 3:** `uv add pandas scikit-learn lightgbm mlflow matplotlib`; implement `colombia.py` as SQL against the audit views.
- [ ] **Step 4:** `uv run pytest -q` → all PASS; `uv run ruff check .` → clean.
- [ ] **Step 5:** Commit `feat: OCDS-inspired canonical schema with Colombia adapter`.

---

### Task 2: Labels and closure

**Files:**
- Create: `src/procurement_risk/features/__init__.py`, `src/procurement_risk/features/labels.py`, `tests/features/__init__.py`, `tests/features/test_labels.py`

**Interfaces:**
- Consumes: `canonical_contracts`, `canonical_amendments`.
- Produces: `build_labels(con, as_of: date, grace_days: int = 180) -> None` creating table `labels(contract_id, is_closed BOOLEAN, has_value_addition BOOLEAN, has_time_extension BOOLEAN, observable_at TIMESTAMP)`:
  - `is_closed = current_end_at <= as_of - grace_days`;
  - `has_value_addition` = any amendment of kind `value_addition` or `value_addition_text`;
  - `has_time_extension = coalesce(added_days, 0) > 0` OR any amendment of kind `extension`;
  - `observable_at = current_end_at + grace_days` (when the label can be trusted; used by Task 3). Labels of open contracts are NULL.

- [ ] **Step 1: Write failing tests:**
  - `test_text_recovered_addition_counts`: a contract with only a `value_addition_text` amendment → `has_value_addition is True`.
  - `test_open_contract_has_null_labels`: end date 30 days before `as_of` → `is_closed False`, labels NULL.
  - `test_extension_from_added_days`.
  - `test_observable_at_is_end_plus_grace`.
- [ ] **Step 2:** `uv run pytest tests/features/test_labels.py -v` → FAIL.
- [ ] **Step 3:** Implement `labels.py`.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: labels with text-recovered value additions and end-date closure`.

---

### Task 3: Point-in-time history features

**Files:**
- Create: `src/procurement_risk/features/history.py`, `tests/features/test_history.py`

**Interfaces:**
- Consumes: `canonical_contracts`, `labels`.
- Produces: `build_history(con, key: str, prefix: str, global_rates: dict[str, float], prior_strength: float = 20.0) -> None` (`global_rates` keys: `"has_value_addition"`, `"has_time_extension"`) creating table `history_<prefix>(contract_id, <prefix>_prior_n, <prefix>_prior_value_addition_rate, <prefix>_prior_extension_rate)`, called with `key="buyer_id", prefix="buyer"` and `key="supplier_key", prefix="supplier"`.
  - Events: one per closed contract with a non-null key, at time `observable_at`, carrying its two labels.
  - For each contract, aggregate the events of the same key with `observable_at < signed_at` (strictly). Implementation: per key, cumulative counts/sums ordered by `observable_at`, then `ASOF LEFT JOIN` on `key` and `signed_at > observable_at`.
  - Rates are smoothed toward the global training-period rate: `(sum + prior_strength * global_rate) / (n + prior_strength)`; with no prior events `n = 0` and rate = global rate. `global_rates` are computed by the caller (Task 4) from closed contracts with `signed_at < 2023-01-01` only (train period), so no validation/test label shapes the prior.

- [ ] **Step 1: Write failing tests** (Review Focus 1):
  - `test_history_excludes_own_label`: one entity, one contract → `buyer_prior_n == 0`.
  - `test_history_excludes_not_yet_observable`: contract A observable on 2022-06-01; contract B signed 2022-06-01 (same day) → B sees `n == 0`; contract C signed 2022-06-02 → sees `n == 1`.
  - `test_history_separates_keys`: events of entity X never count for entity Y.
  - `test_rate_is_smoothed`: 2 prior events both positive, `global_rate=0.1`, `prior_strength=20` → rate `== (2 + 2) / 22`.
  - `test_null_supplier_key_gets_global_rate`.
- [ ] **Step 2:** `uv run pytest tests/features/test_history.py -v` → FAIL.
- [ ] **Step 3:** Implement `history.py`.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: point-in-time buyer and supplier history features`.

---

### Task 4: Feature assembly, dataset and validation

**Files:**
- Create: `src/procurement_risk/features/build.py`, `src/procurement_risk/validate.py`, `tests/features/test_build.py`, `tests/test_validate.py`
- Modify: `src/procurement_risk/__main__.py` (command `build-dataset`)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces in `build.py`:
  - `CATEGORICAL_FEATURES: tuple[str, ...] = ("buyer_department", "buyer_order", "buyer_sector", "buyer_branch", "buyer_centralized", "procurement_method", "contract_type", "category_segment", "funding_source")`
  - `NUMERIC_FEATURES: tuple[str, ...] = ("log_award_value", "log_tender_budget", "award_to_budget_ratio", "planned_duration_days", "days_publication_to_signing", "days_signing_to_start", "n_bidders", "single_bidder", "n_responses", "n_invited", "n_lots", "signing_month", "signed_in_december", "supplier_is_natural_person", "supplier_is_sme", "supplier_is_group", "advance_payment_enabled", "extendable_clause", "buyer_prior_n", "buyer_prior_value_addition_rate", "buyer_prior_extension_rate", "supplier_prior_n", "supplier_prior_value_addition_rate", "supplier_prior_extension_rate")`
  - `TARGETS = ("has_value_addition", "has_time_extension")`
  - `build_dataset(raw_dir: Path, out_path: Path, as_of: date) -> DatasetSummary` — runs Tasks 1–3, writes one Parquet with `contract_id, signed_at, buyer_id`, all features and both targets **for closed contracts only**; returns `@dataclass DatasetSummary(n_rows, n_without_process, positive_rate: dict[str, float])`.
  - Derived features: `log_award_value = ln(1 + award_value)`; `award_to_budget_ratio = award_value / tender_budget` (null if budget ≤ 0); `days_publication_to_signing` null if negative (Review Focus 3); `days_signing_to_start` null if < −30; `single_bidder = n_bidders = 1`; booleans as 0/1.
- Produces in `validate.py`: `class DatasetValidationError(ValueError)`; `validate_dataset(df: pandas.DataFrame) -> None` raising when: duplicate `contract_id` (Review Focus 5); any target rate outside `[0.005, 0.6]`; any feature 100% null; a forbidden column present (`valor_del_contrato`, `current_end_at`, `added_days`, `estado_contrato`).
- CLI: `python -m procurement_risk build-dataset --raw data/raw --out data/processed/dataset.parquet --as-of 2026-11-14`.

- [ ] **Step 1: Write failing tests:**
  - `test_negative_publication_gap_is_null` (Review Focus 3).
  - `test_rows_without_process_are_kept_and_counted` (Review Focus 2): `summary.n_without_process == 1`, row present.
  - `test_only_closed_contracts_in_dataset`.
  - `test_dataset_has_no_forbidden_columns`.
  - `test_validate_rejects_duplicates` (Review Focus 5), `test_validate_rejects_all_null_feature`, `test_validate_rejects_implausible_rate`.
- [ ] **Step 2:** `uv run pytest tests/features/test_build.py tests/test_validate.py -v` → FAIL.
- [ ] **Step 3:** Implement `build.py`, `validate.py`, CLI command (it calls `validate_dataset` before writing).
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: leakage-safe training dataset with validation`.

---

### Task 5: Temporal split, metrics and baselines

**Files:**
- Create: `src/procurement_risk/model/__init__.py`, `src/procurement_risk/model/split.py`, `src/procurement_risk/model/metrics.py`, `src/procurement_risk/model/baselines.py`, `tests/model/__init__.py`, `tests/model/test_split.py`, `tests/model/test_metrics.py`, `tests/model/test_baselines.py`

**Interfaces:**
- Produces:
  - `split.temporal_split(df, train_end=date(2023,1,1), valid_end=date(2023,7,1), test_end=date(2025,1,1)) -> Splits` with `@dataclass Splits(train, valid, test: pandas.DataFrame)`; rows signed on or after `test_end` are dropped.
  - `metrics.evaluate(y_true: np.ndarray, y_score: np.ndarray, top_share: float = 0.05) -> dict[str, float]` with keys `pr_auc, roc_auc, brier, log_loss, precision_at_top, recall_at_top, positive_rate`.
  - `baselines.BaseRate`, `baselines.BuyerRate`, `baselines.LogisticBaseline`, each with `fit(train_df, target) -> self` and `predict_proba(df) -> np.ndarray` (probability of the positive class). `BuyerRate` returns `buyer_prior_value_addition_rate` for `has_value_addition` and `buyer_prior_extension_rate` for `has_time_extension` (already point-in-time). `LogisticBaseline` = scikit-learn pipeline: one-hot (`handle_unknown="ignore"`, `min_frequency=50`) on `CATEGORICAL_FEATURES`, median-impute + standard-scale `NUMERIC_FEATURES`, `LogisticRegression(max_iter=1000, class_weight=None)`.

- [ ] **Step 1: Write failing tests:**
  - `test_split_boundaries`: rows on 2022-12-31 / 2023-01-01 / 2023-06-30 / 2023-07-01 / 2025-01-01 land in train / valid / valid / test / dropped.
  - `test_evaluate_perfect_and_random`: perfect scores → `pr_auc == 1.0`; constant scores → `pr_auc == positive_rate` (approx).
  - `test_precision_at_top`: 100 rows, top 5 all positive → `precision_at_top == 1.0`.
  - `test_base_rate_is_constant_train_rate`.
  - `test_logistic_baseline_handles_unseen_category`.
- [ ] **Step 2:** `uv run pytest tests/model -v` → FAIL.
- [ ] **Step 3:** Implement the three modules.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: temporal split, metrics and baselines`.

---

### Task 6: LightGBM, calibration and MLflow

**Files:**
- Create: `src/procurement_risk/model/train.py`, `tests/model/test_train.py`
- Modify: `src/procurement_risk/__main__.py` (command `train`)

**Interfaces:**
- Consumes: `Splits`, `evaluate`, baselines, feature lists.
- Produces:
  - `train_lightgbm(splits: Splits, target: str, params: dict | None = None) -> RiskModel`. Defaults: `objective="binary", learning_rate=0.05, num_leaves=63, min_child_samples=100, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, n_estimators=2000`, early stopping (100 rounds) on the **validation** split by `average_precision`; categoricals passed as pandas `category` dtype with categories fixed from train.
  - `class RiskModel` with `predict_raw(df) -> np.ndarray`, `predict_proba(df) -> np.ndarray` (calibrated), `booster`, `calibrator: IsotonicRegression`, `feature_names`. The calibrator is fitted on validation predictions only (Review Focus 4).
  - `run_experiment(dataset_path: Path, target: str, tracking_uri: str = "sqlite:///mlflow.db") -> dict[str, dict[str, float]]` — trains baselines and LightGBM, evaluates all on the test split, logs params/metrics per model to MLflow experiment `amendment-risk-<target>`, logs the LightGBM model, registers it as `amendment-risk-<target>`, saves `data/models/<target>/model.joblib`, returns `{model_name: test_metrics}`.
  - CLI: `python -m procurement_risk train --dataset data/processed/dataset.parquet --target has_value_addition` (and `--target has_time_extension`).

- [ ] **Step 1: Write failing tests** on a synthetic dataset (2,000 rows, signal in one numeric feature, dates across all three periods):
  - `test_lightgbm_beats_base_rate_on_synthetic`: test PR-AUC of LightGBM > base rate PR-AUC + 0.1.
  - `test_calibrator_sees_only_validation_rows` (Review Focus 4): wrap `IsotonicRegression.fit` (monkeypatch) and assert the number of rows it receives equals `len(splits.valid)`.
  - `test_calibrated_probabilities_in_unit_interval`.
  - `test_run_experiment_logs_to_mlflow`: `tracking_uri=f"sqlite:///{tmp_path}/m.db"` → MLflow has one run per model and a registered model version.
- [ ] **Step 2:** `uv run pytest tests/model/test_train.py -v` → FAIL.
- [ ] **Step 3:** Implement `train.py` and CLI command.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: calibrated LightGBM with MLflow tracking`.

---

### Task 7: Explanations, figures and model card

**Files:**
- Create: `src/procurement_risk/model/explain.py`, `src/procurement_risk/model/report.py`, `tests/model/test_explain.py`, `tests/model/test_report.py`
- Modify: `src/procurement_risk/model/train.py` (`run_experiment` calls the report), `.gitignore` (nothing new; `docs/figures/` is committed)

**Interfaces:**
- Produces:
  - `explain.contributions(model: RiskModel, df) -> pandas.DataFrame` — `booster.predict(..., pred_contrib=True)`, columns = features + `bias`.
  - `explain.top_signals(model, df, k: int = 3) -> list[list[tuple[str, float]]]` — per row, the k features with the largest positive contribution.
  - `explain.global_importance(model, df) -> pandas.Series` — mean |contribution| per feature, sorted descending.
  - `report.write_figures(results, model, test_df, target, out_dir=Path("docs/figures")) -> list[Path]` writing `<target>-pr-curves.png` (all models), `<target>-calibration.png` (10 quantile bins, calibrated vs raw), `<target>-importance.png` (top 15 global importance). Figures plot aggregates only.
  - `report.write_model_card(all_results: dict[str, dict], dataset_summary, out_path=Path("docs/model-card.md")) -> None`: sections Intended use (with the disclaimer), Data (period, n rows, positive rates, closure rule, label definitions from the audit), Features (lists, exclusions with reasons), Evaluation (test-split table per target and model), Limitations (label noise from the 84%-precision text matcher; stale `estado_contrato`; Colombia only; one-day data lag), Ethical considerations (no supplier rankings; natural persons hashed).

- [ ] **Step 1: Write failing tests:**
  - `test_contributions_sum_to_raw_score`: row sums of contributions == booster raw (log-odds) prediction (atol 1e-6).
  - `test_top_signals_returns_k_positive_features`.
  - `test_model_card_contains_disclaimer_and_metrics`: contains "not allegations of wrongdoing" and the PR-AUC values passed in.
  - `test_figures_are_written`: three PNG files exist and are non-empty.
- [ ] **Step 2:** `uv run pytest tests/model/test_explain.py tests/model/test_report.py -v` → FAIL.
- [ ] **Step 3:** Implement `explain.py`, `report.py`; hook into `run_experiment`.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat: SHAP explanations, evaluation figures and model card`.

---

### Task 8: Run on real data and publish results

- [ ] **Step 1: Widen the raw data** (requires `PII_HASH_SALT` from `.env`; run in background, ~1–2 h):
  - `uv run python -m procurement_risk ingest contracts --from 2019-01-01 --to 2025-01-01 --out data/raw`
  - `uv run python -m procurement_risk ingest processes --from 2018-07-01 --to 2025-01-01 --out data/raw`
  - (amendments already cover the whole table; re-run only if older than 7 days)
- [ ] **Step 2:** `uv run python -m procurement_risk build-dataset --raw data/raw --out data/processed/dataset.parquet --as-of 2026-11-14` → prints the summary; confirm validation passed, `n_without_process / n_rows < 0.01`, value-addition rate between 5% and 20% (audit estimate ~10%).
- [ ] **Step 3:** `uv run python -m procurement_risk train --dataset data/processed/dataset.parquet --target has_value_addition`, then the same with `--target has_time_extension`.
- [ ] **Step 4: Sanity checks before trusting numbers:** LightGBM beats every baseline on test PR-AUC; if test PR-AUC is suspiciously high (> 0.9) look for leakage by checking the top-15 importance for any post-signing signal and stop to investigate (superpowers:systematic-debugging) instead of publishing.
- [ ] **Step 5:** Update `README.md`: status → Phase 1 complete; a "Results" section with the test-metric table (both targets, all models), the three figures per target, a link to `docs/model-card.md`, and a "How it works" paragraph (canonical schema, point-in-time history, temporal split, calibration).
- [ ] **Step 6:** `uv run pytest -q` and `uv run ruff check .` → PASS/clean; grep committed docs and figures for supplier names from the raw data (none expected).
- [ ] **Step 7:** Commit `docs: phase 1 results, figures and model card`. Show the owner the results table and figures, and push to `origin main` only after their OK in chat (public repo); then confirm CI green with `gh run list --workflow ci.yml --limit 1`.
