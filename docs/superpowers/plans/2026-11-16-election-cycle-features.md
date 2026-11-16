# Election-cycle features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give both models election-calendar features known at signing time, and let each model carry its own feature list so a bundle can mix old and new models.

**Architecture:** Models prepare their input from their own `feature_names`; `load_bundle` accepts any model whose features this code can compute. The calendar is a constant turned into a DuckDB `VALUES` table and used by the shared `FEATURE_SELECT`, so training, API and website compute identical values.

**Tech Stack:** Python 3.12, DuckDB, LightGBM, pandas, pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-election-cycle-features-design.md`

## Global Constraints

- No new API request fields; features derive from `signed_at`, `planned_start_at`, `planned_duration_days`.
- Restriction window: 122 days before an election day, inclusive of the election day itself.
- Election days: 2018-03-11, 2018-05-27, 2019-10-27, 2022-03-13, 2022-05-29, 2023-10-29, 2026-03-08, 2026-05-31, 2027-10-31.
- Public wording never says elections cause amendments; never "corruption"/"fraud".
- Final feature set = the variant the validation run picked (Task 0).

## Review Focus

- Missing `planned_start_at` or `planned_duration_days`: end-based features are NULL, not computed from a fake date (test in Task 2).
- Signing after the last calendar date: `days_*_to_next_election` is NULL, not negative (test in Task 2).
- An old bundle (pre-change pickles, metadata `features` = old list) still loads and scores (test in Task 1).
- A bundle naming a feature this code cannot compute is rejected with `BundleError` (test in Task 1).
- API scoring and training produce equal election features for the same contract (parity test, Task 2).

---

### Task 0: Validate (no code)

- [ ] Run `scratchpad/election_validate.py` (real `train_lightgbm`, 3 seeds, both targets, variants base / S / S+days_to_next).
- [ ] Keep the smallest variant whose mean extension PR-AUC beats base by more than 2 std, and whose value-addition PR-AUC is not below base by more than 1 std. If none, stop and report.

### Task 1: Per-model feature lists

**Files:** Modify `src/procurement_risk/model/train.py`, `src/procurement_risk/serving/bundle.py`, `src/procurement_risk/serving/scoring.py`. Test `tests/serving/test_bundle.py`, `tests/model/test_train.py`.

**Interfaces:**
- Produces: `RiskModel.frame(df)` uses `self.feature_names` and `self.categories`; `_prepare(df, categories, features=FEATURES)`; `load_bundle` raises `BundleError` only when a model's `feature_names` contain a name not in `FEATURES`. Metadata `features` = union of model features, in `FEATURES` order.

- [ ] Test `test_model_with_fewer_features_still_scores`: build a RiskModel via `train_lightgbm` with the training feature list monkeypatched to drop `extendable_clause`; restore it; assert `model.feature_names` lacks `extendable_clause` and `predict_raw(df)` on the full frame returns `len(df)` values.
- [ ] Test `test_bundle_accepts_subset_and_rejects_unknown_features`: demo bundle with metadata `features` minus one feature loads; with an extra `"made_up"` feature raises `BundleError` matching `made_up`.
- [ ] Run, see both fail. Implement. Run full suite. Commit `feat: models carry their own feature list`.

### Task 2: Election-calendar features

**Files:** Create `src/procurement_risk/features/elections.py`. Modify `features/build.py` (`NUMERIC_FEATURES`, `FEATURE_SELECT`), `serving/scoring.py` (register calendar table), `serving/labels.py`, `ops/config.py` (`EXPECTED_DRIFT`), `model/report.py` (feature bullet). Test `tests/features/test_elections.py`, `tests/features/test_build.py`.

**Interfaces:**
- Produces: `ELECTION_DAYS: tuple[date, ...]`, `RESTRICTION_DAYS = 122`, `register_calendar(con) -> None` creating table `election_days(day DATE)`. `FEATURE_SELECT` requires that table.

- [ ] Tests in `test_elections.py`:
  - `test_calendar_covers_the_next_year`: `max(ELECTION_DAYS) >= date.today() + timedelta(days=365)`.
  - `test_restriction_flags`: contract signed 2023-08-01 → `signed_in_restriction == 1`; signed 2023-01-10 with start 2023-01-10 and 200 days → `planned_end_in_restriction == 1` and `days_end_to_next_election == 92`; signed 2024-03-01, 30 days → both 0.
  - `test_missing_duration_gives_null_end_features`.
  - `test_after_calendar_gives_null_days` (signed 2028-01-01).
- [ ] Extend `test_feature_frame_without_labels_matches_training_features` to include the new columns (it already compares all features).
- [ ] Run, fail, implement, run full suite (`uv run pytest -q`, `uv run ruff check src tests`). Commit `feat: election-calendar features`.

### Task 3: Docs and website copy

- [ ] Model card feature bullet and Limitations line: the features mark Ley 996 restriction windows; they describe a pattern, not a cause.
- [ ] `docs/operations.md`: extending `ELECTION_DAYS` when the calendar test fails.
- [ ] Methodology page: only if it lists features (check `web/src/routes/Methodology.tsx`).
- [ ] Commit `docs: election-calendar features`.
