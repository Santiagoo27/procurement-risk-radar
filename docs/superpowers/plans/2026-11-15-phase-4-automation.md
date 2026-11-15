# Phase 4: Automation and Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Load the `dataviz` skill before any chart or table-of-numbers UI.

**Goal:** Make the system maintain itself. A weekly job refreshes the data, checks its quality, rescores open contracts, monitors drift and realized performance, measures amendment size from the snapshot archive, and updates the website. A monthly job retrains both models and, if they beat the production models, opens a pull request for the owner to approve. A new "Buyers" page ranks entities by department.

**Owner decisions (2026-11-15):**
- **Model promotion needs the owner's approval** through a pull request. Nothing reaches production automatically.
- **Website data refreshes weekly.** The nightly SECOP snapshot archive keeps running unchanged.

**Architecture:**
- **Weekly (`weekly-refresh.yml`, Sundays):**
  1. Download SECOP again into the runner.
  2. Run quality checks.
  3. `export-web-data` with the production bundle, plus `monitoring.json` and `amendment-size.json`.
  4. Commit `web/public/data` to `main` when it changed. Vercel redeploys.
- **Monthly (`monthly-retrain.yml`, 1st of the month):**
  1. Download and run quality checks.
  2. Build the dataset with a rolling temporal split.
  3. Train challengers and score the champion (current bundle) on the same new test period.
  4. Apply the promotion gate.
  5. If the gate passes: publish a draft release with the new bundle and open a PR. The PR switches `Dockerfile.render`'s `BUNDLE_TAG` and updates the model card, figures and README metrics. Merging it makes Render deploy the new model.
- **On failure:** any pipeline failure opens or updates one GitHub issue per workflow.
- **Source of truth:** `Dockerfile.render` `ARG BUNDLE_TAG` is the single source of truth for the production model.

**Tech Stack:** existing Python package, GitHub Actions (`gh` CLI), DuckDB, React page in `web/`.

**Spec:** `docs/superpowers/specs/2026-11-14-procurement-risk-design.md` §8 Phase 4 (nightly scoring, scheduled retraining with promotion gate, data-quality checks, drift reports, snapshot-based severity).

## Global Constraints

- **Privacy:** raw SECOP downloads (supplier names, free text) never leave the runner. They are not cached, uploaded or committed. Only the existing privacy-safe exports are published. `PII_HASH_SALT` comes from the repository secret (already set).
- No model change reaches production without a merged PR. The workflow may create **draft** releases and PRs. Only the owner merges.
- The weekly job must finish within GitHub's 6-hour limit on `ubuntu-latest` (target under 2 h). The monthly job also stays under 6 h.
- English everywhere. Monitoring text is neutral and never accusatory.
- Commits made by workflows use the `github-actions[bot]` identity, with messages prefixed `data:` (weekly refresh) or `model:` (monthly promotion PR). Commits made while implementing this plan keep the usual attribution trailer.
- Thresholds (decided here, keep them in one module `procurement_risk/ops/config.py`):
  - **Quality.** Contracts row count ≥ 95% of the previous run's. Processes row count ≥ 1,000,000. Required columns no more than 5% null.
  - **Promotion gate, for both targets:**
    - challenger PR-AUC ≥ champion PR-AUC − 0.005;
    - challenger Brier ≤ champion Brier × 1.02;
    - for at least one target, challenger PR-AUC ≥ champion PR-AUC + 0.002, so the release brings a real gain.
  - **Drift.** A feature's PSI above 0.2 is "shifted". Monitoring compares contracts signed in the last 90 days against the training period.
  - **Rolling split.** `test_end = as_of − 365 days`. The test window covers the 18 months before that. Validation covers the 6 months before the test window. Training uses everything earlier.

## Review Focus

1. A partial SECOP outage, like the 2026-11-15 truncation of the processes dataset to 1,000 rows. Expected: quality checks fail the run with a clear message, the issue opens, and no data or model is published from a broken download. Test in Task 2.
2. The champion and challenger evaluated on different periods or rows, which would make the gate meaningless. Expected: both are scored on the identical test frame. Test in Task 3.
3. The weekly commit loop: the workflow commits data, which triggers CI and Vercel. It must not re-trigger itself or commit when nothing changed. Expected: `[skip ci]` is absent (CI should run) and the commit happens only on a diff. Checked in Task 6.
4. Snapshot-based size estimates computed on too few contracts, or on value changes that are corrections downward. Expected: only increases count as additions, n is always shown, and the result is "not enough data" below 100 contracts. Test in Task 5.
5. Drift metrics on empty or tiny recent windows (holidays, outages). Expected: PSI is null with a reason when either window has fewer than 500 rows. No crash. Test in Task 4.

---

## File Structure

```
src/procurement_risk/ops/__init__.py
src/procurement_risk/ops/config.py        # all thresholds above
src/procurement_risk/ops/quality.py       # data-quality checks on raw parquet
src/procurement_risk/ops/promotion.py     # rolling split, champion vs challenger, gate, report
src/procurement_risk/ops/monitoring.py    # PSI drift, score shift, realized performance
src/procurement_risk/ops/severity.py      # amendment size from the snapshot archive
scripts/ingest_all.sh                     # shared download step for workflows
.github/workflows/weekly-refresh.yml
.github/workflows/monthly-retrain.yml
.github/actions/report-failure/action.yml # composite: open/update a GitHub issue
web/src/routes/Buyers.tsx (+ test)        # rankings page
web/src/routes/Methodology.tsx            # "Model health" + "How big are additions" sections
tests/ops/*
docs/operations.md                        # how the automation works, how to approve a model PR
```

---

### Task 1: "Buyers" rankings page

**Files:** Create `web/src/routes/Buyers.tsx`, `web/src/routes/Buyers.test.tsx`. Modify `web/src/App.tsx` (route `/buyers`, nav item "Buyers").

**Interfaces:** reads `entities.json`, `departments.json` and `municipalities.json` through the existing loaders. The URL query holds the state: `?dpto=05&mpio=&metric=value_addition&min=100&q=`.

The page contains:
- A department `<select>` (all departments, then by name) and a municipality select once a department is chosen.
- A metric toggle: value additions or time extensions.
- A minimum-sample select: 30, 100 or 500, default 100.
- A name search, accent-insensitive.
- A sortable table: buyer (linking to the entity page), municipality, rate, n closed, and a difference against Colombia in percentage points.
- Pagination of 50 rows.
- A note at the top: "A high rate means this buyer's contracts often change after signing compared with what was planned. It is not a finding of wrongdoing."

- [ ] **Step 1: Failing tests:**
  - filtering by department;
  - buyers below `min` are excluded;
  - the metric switch re-sorts;
  - search is accent-insensitive (`"medellin"` finds `"MEDELLÍN"`);
  - the URL query restores state;
  - every row shows n.
- [ ] **Step 2:** Implement → `npx vitest --run` PASS, typecheck clean. Visually check desktop and 375 px.
- [ ] **Step 3:** Commit `feat: buyers rankings page`.

---

### Task 2: Data-quality checks

**Files:** Create `src/procurement_risk/ops/__init__.py`, `ops/config.py`, `ops/quality.py`, `tests/ops/test_quality.py`. Modify `__main__.py` (command `check-quality`).

**Interfaces:**
- `QualityReport(dataclass)`: `passed: bool`, `checks: list[Check(name, passed, detail)]`. Method `to_markdown()`.
- `check_raw(raw_dir: Path, previous: dict | None) -> QualityReport`. It checks:
  - contracts, amendments and processes row counts, compared with `previous` counts when given;
  - processes row count ≥ `MIN_PROCESS_ROWS` (1,000,000);
  - the maximum `fecha_de_firma` is within the last 14 days of the run date;
  - null rate ≤ 5% for `id_contrato`, `fecha_de_firma`, `codigo_entidad`, `valor_del_contrato`.
- CLI: `python -m procurement_risk check-quality --raw data/raw --previous web/public/data/quality.json --out data/quality.json`.
  - Exits 4 on failure.
  - Always writes the report.
  - Prints the Markdown version (the workflow puts it in the job summary).
- The weekly export copies the passing report's counts to `web/public/data/quality.json`, to serve as "previous" next week.

- [ ] **Step 1: Failing tests:**
  - `test_truncated_processes_fail` (Review Focus 1): 1,000 process rows → `passed False` with "processes" in the detail.
  - `test_row_drop_against_previous_fails`.
  - `test_stale_data_fails`.
  - `test_healthy_data_passes`.
  - `test_cli_exit_code_4_on_failure`.
- [ ] **Step 2:** Implement → PASS.
- [ ] **Step 3:** Commit `feat: data-quality checks for SECOP downloads`.

---

### Task 3: Rolling split, champion vs challenger, promotion gate

**Files:** Create `ops/promotion.py`, `tests/ops/test_promotion.py`. Modify `model/split.py` (add `rolling_split_dates`) and `__main__.py` (command `retrain`).

**Interfaces:**
- `split.rolling_split_dates(as_of: date) -> tuple[date, date, date]`: returns `(train_end, valid_end, test_end)` following the Global Constraints rule.
- `promotion.compare(dataset: DataFrame, champion: Bundle, challengers: dict[str, RiskModel], as_of) -> dict`. Per target it returns `{"champion": metrics, "challenger": metrics, "n_test": int, "test_period": [start, end]}`.
  - Champion and challenger are evaluated on **the same** test frame, with `evaluate(y, raw, y_prob=calibrated)`.
- `promotion.decide(comparison) -> Decision(promote: bool, reasons: list[str])`, applying the gate from `ops/config.py`.
- `promotion.write_report(comparison, decision, path)`: a Markdown table per target with champion, challenger and delta, plus the decision and its reasons. This becomes the PR body.
- CLI: `python -m procurement_risk retrain --raw data/raw --bundle serving_bundle --as-of YYYY-MM-DD --out data/retrain`.
  1. Build the dataset.
  2. Split with `rolling_split_dates`.
  3. Train challengers (`train_lightgbm` + baselines for the report).
  4. Compare and decide.
  5. Write `data/retrain/report.md` and `decision.json`.
  6. When promoting, also write `data/retrain/models/<target>/{model.joblib,metrics.json}`, ready for `export-bundle`.

- [ ] **Step 1: Failing tests:**
  - `test_rolling_split_dates`: as_of 2026-11-14 → `(train_end=2023-11-14, valid_end=2024-05-14, test_end=2025-11-14)`, with months stepped by calendar month.
  - `test_champion_and_challenger_share_test_rows` (Review Focus 2): spy on `evaluate` and assert identical `y` arrays.
  - `test_gate_rejects_worse_challenger`, `test_gate_requires_some_gain`, `test_gate_promotes_better_challenger`.
  - `test_report_contains_both_targets_and_decision`.
- [ ] **Step 2:** Implement → PASS. Use the demo bundle and the synthetic dataset for fixtures.
- [ ] **Step 3:** Commit `feat: champion vs challenger comparison and promotion gate`.

---

### Task 4: Monitoring (drift and realized performance)

**Files:** Create `ops/monitoring.py`, `tests/ops/test_monitoring.py`. Modify `__main__.py` (command `monitor`), `web/src/lib/data.ts` (`loadMonitoring`), `web/src/routes/Methodology.tsx` (section "Model health").

**Interfaces:**
- `monitoring.psi(reference: Series, current: Series, bins=10) -> float | None`.
  - Quantile bins come from the reference for numerics, and categories from the reference for categoricals.
  - Returns `None` when either side has fewer than 500 non-null values.
- `monitoring.build_report(features_df, labels_df, bundle, as_of) -> dict`:
  - `as_of`;
  - `windows: {reference: [train_start, train_end], current: [as_of−90d, as_of]}`;
  - `feature_drift: [{feature, label, psi, shifted}]`, sorted by PSI;
  - `score_shift`: mean and quantiles of calibrated value-addition probability, current against reference;
  - `realized`: the bundle model evaluated on contracts that **closed in the last 180 days** and were signed after the bundle's training data. Gives PR-AUC, positive rate and n, or `null` with a reason.
  - `status`: `ok`, `watch` (≥ 1 shifted feature or realized PR-AUC 0.03 below the bundle test PR-AUC) or `insufficient_data`.
- Written to `web/public/data/monitoring.json` by the weekly job (CLI `monitor --raw … --bundle … --out web/public/data/monitoring.json --as-of …`).
- Methodology "Model health" shows:
  - the last check date and status;
  - the top 5 features by PSI, as a small table with the PSI value and a "shifted" tag;
  - realized PR-AUC against the test PR-AUC, with n.

- [ ] **Step 1: Failing tests:**
  - `test_psi_zero_for_identical_distributions`;
  - `test_psi_detects_shift` (> 0.2 for a shifted normal);
  - `test_psi_none_for_tiny_windows` (Review Focus 5);
  - `test_report_status_insufficient_data`;
  - web `Methodology.test.tsx` extended: renders the status and the top shifted feature from a mocked `monitoring.json`.
- [ ] **Step 2:** Implement → PASS.
- [ ] **Step 3:** Commit `feat: drift and realized-performance monitoring`.

---

### Task 5: Amendment size from the snapshot archive

**Files:** Create `ops/severity.py`, `tests/ops/test_severity.py`. Modify `__main__.py` (command `amendment-size`) and `web/src/routes/Methodology.tsx` (section "How big are additions?").

**Interfaces:**
- `severity.load_history(snapshot_dir: Path) -> DataFrame`: concatenates `baseline-*.parquet` and `changes-*.parquet` from the `snapshots` release.
- `severity.value_changes(history) -> DataFrame`: per contract, the first observed `valor_del_contrato` and the latest one. Keeps contracts whose latest value is **higher** than the first observed value (Review Focus 4: decreases and corrections are excluded), with `increase_pct`.
- `severity.summary(changes, min_n=100) -> dict`: `{since, n_contracts_observed, n_increased, median_increase_pct, p75, p90, share_over_30pct}`. These are `null` with `reason` when `n_increased < min_n`.
- The weekly job downloads the release assets into `data/snapshots/` with `gh release download snapshots` and writes `web/public/data/amendment-size.json`.
- Methodology adds one paragraph and the numbers, labelled "early, since 2026-11-14, n = …".

- [ ] **Step 1: Failing tests:**
  - `test_only_increases_count`;
  - `test_first_and_latest_values_per_contract`;
  - `test_summary_not_enough_data_below_min_n`;
  - `test_increase_pct`.
- [ ] **Step 2:** Implement → PASS.
- [ ] **Step 3:** Commit `feat: amendment size from the snapshot archive`.

---

### Task 6: Workflows

**Files:** Create `scripts/ingest_all.sh`, `.github/actions/report-failure/action.yml`, `.github/workflows/weekly-refresh.yml`, `.github/workflows/monthly-retrain.yml`, `docs/operations.md`. Modify `README.md` (an "Operations" section linking to `docs/operations.md`).

**Interfaces:**
- **`scripts/ingest_all.sh AS_OF`:** contracts 2019-01-01 → AS_OF+1, all amendments, and processes 2018-07-01 → AS_OF+1 into `data/raw`, using the existing CLI. Requires `PII_HASH_SALT`.
- **`report-failure` composite action** (inputs `title` and `body`): `gh issue list --search "in:title <title>" --state open`. If an issue exists it comments on it; otherwise it creates one with the label `pipeline`.
- **`weekly-refresh.yml`:**
  - Triggers: `schedule: "0 9 * * 0"` and `workflow_dispatch`.
  - Permissions: `contents: write, issues: write`.
  - `timeout-minutes: 300`.
  - Steps:
    1. Checkout, uv sync (base + train extras not needed).
    2. Read `BUNDLE_TAG` from `Dockerfile.render`.
    3. Download that release's bundle and verify its sha256.
    4. `ingest_all.sh`, then `check-quality` (on failure, run `report-failure` and stop).
    5. `gh release download snapshots` → `amendment-size`.
    6. `export-web-data`, then `monitor`.
    7. If `git status --porcelain web/public/data` is non-empty, commit as `github-actions[bot]` with `data: weekly refresh <date>` and push.
    8. `report-failure` on any failed step.
- **`monthly-retrain.yml`:**
  - Triggers: `schedule: "0 6 1 * *"` and `workflow_dispatch`.
  - Permissions: `contents: write, pull-requests: write, issues: write`.
  - Steps:
    1. Checkout, `uv sync --extra train`.
    2. Download the production bundle.
    3. `ingest_all.sh`, `check-quality`.
    4. `retrain`.
    5. Upload `report.md`, `decision.json` and `mlflow.db` as workflow artifacts.
    6. If `decision.promote`:
       - export the bundle as `model-<as_of>`;
       - tar it and write its sha256;
       - `gh release create model-<as_of> --draft` with the assets;
       - create branch `model/<as_of>`: update `Dockerfile.render` `BUNDLE_TAG`, regenerate `docs/model-card.md` and `docs/figures/*` from the retrain outputs, and update the README results table;
       - `gh pr create --title "model: promote <as_of>" --body-file report.md`.
    7. If not promoting, write the report to the job summary only.
  - Draft release: the PR description tells the owner to publish the draft release before merging. Render cannot download draft assets. `docs/operations.md` explains the two clicks.
- **`docs/operations.md`:** schedules, what each job does, how to approve a model PR (publish the release, then merge), how to read `monitoring.json`, how to re-run a job by hand, and what to do when a pipeline issue opens.
- **Review Focus 3:** the weekly commit touches only `web/public/data` and happens only on a diff. CI runs on it; that is intended. No workflow triggers on `push` to that path except CI.

- [ ] **Step 1:** Write the script, action, workflows and docs. Lint the YAML with `uvx yamllint .github` (relaxed config) and `npx --yes @action-validator/cli@<pinned>` (or `actionlint` via Docker if available). Expected: no errors.
- [ ] **Step 2:** Commit `ci: weekly refresh and monthly retrain workflows`.

---

### Task 7: Run it for real (owner OK required for each push)

- [ ] **Step 1 (owner action):** in the repo's Settings → Actions → General, enable "Allow GitHub Actions to create and approve pull requests". It is needed to open the model PR. The executor gives the exact path.
- [ ] **Step 2:** After the owner OKs the push, push `main`. Then `gh workflow run weekly-refresh.yml` and `gh run watch`. Expected outcomes:
  - **SECOP processes still truncated:** the run **fails at check-quality**, an issue "Weekly refresh failed" opens with the report, and nothing is committed. This verifies Review Focus 1 live.
  - **Processes restored:** the data commit lands, Vercel redeploys, `summary.json` shows `n_open_scored ≥ 10,000` and the predicted layer turns on.
- [ ] **Step 3:** `gh workflow run monthly-retrain.yml`. Expected: either a "no promotion" job summary with the comparison table, or a draft release plus a PR. The executor reports which, and does not merge.
- [ ] **Step 4:** Update the README status to "Phase 4 complete" with links to `docs/operations.md` and the latest monitoring status. Commit and push after the owner's OK.
