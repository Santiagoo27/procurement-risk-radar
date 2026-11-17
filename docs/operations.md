# Operations

The system keeps itself up to date with three scheduled GitHub Actions workflows. Raw SECOP
downloads, which contain supplier names and free text, stay on the runner and are deleted
with it. Only the privacy-safe exports are published.

| Workflow | When | What it does |
|---|---|---|
| [`snapshot.yml`](../.github/workflows/snapshot.yml) | Every night, 07:00 UTC | Archives every contract whose value or end date changed, as assets of the `snapshots` release. A full baseline is taken on the 1st of each month. |
| [`weekly-refresh.yml`](../.github/workflows/weekly-refresh.yml) | Sundays, 09:00 UTC | Downloads SECOP and checks data quality. Then it rescores open contracts with the production model, updates `monitoring.json` and `amendment-size.json`, and commits `web/public/data` when it changed. Vercel redeploys the site. |
| [`monthly-retrain.yml`](../.github/workflows/monthly-retrain.yml) | 1st of the month, 06:00 UTC | Downloads SECOP, checks quality and retrains both models on a rolling split. It compares them with the production models **on the same test rows** and decides each target on its own. If at least one improved, it publishes a draft release and opens a pull request. |

The production model is whatever `ARG BUNDLE_TAG` in [`Dockerfile.render`](../Dockerfile.render)
points to. The API, the weekly refresh and the website all use that bundle.

## Approving a new model

When the monthly retrain finds a better model, you receive a pull request titled
`model: promote YYYY-MM-DD`. It contains:

- a table comparing the current and the new model on each target (PR-AUC, ROC-AUC, Brier,
  precision in the top 5%), on the same contracts;
- the decision for each target (promote or keep current) and its reasons;
- a link to a **draft** release with the new bundle.

The bundle can mix models. If only the value-addition model improved, the new bundle has the
new value-addition model and the current time-extension model. `metadata.json` →
`model_sources` and the model card say which one was kept and from which release.

To approve:

1. Read the comparison. The gate already required each promoted model to improve PR-AUC by at
   least 0.002 and keep its Brier score within 2% of the current one.
2. Open the draft release (Releases → `model-YYYY-MM-DD` → Edit) and click **Publish
   release**. Render cannot download a draft.
3. Update the results table in `README.md` from the new `docs/model-card.md`, if you want the
   README to show the new numbers.
4. **Merge** the pull request. Render rebuilds the API with the new bundle once CI passes. The
   next weekly refresh rescores the website with it.

The pull request is opened by the workflow's own token, and GitHub does not run other
workflows for those events. CI therefore does not run on it automatically. To get checks
before merging, close and reopen the pull request; that event comes from you, so CI runs.

If an earlier model pull request is still open, the monthly job does not open another one.
Approve or close the open one first.

To reject, close the pull request and delete the draft release.

The promotion gate lives in [`src/procurement_risk/ops/config.py`](../src/procurement_risk/ops/config.py).
It is applied to **each target on its own**: the new model replaces the production one only
if PR-AUC improves by at least 0.002 and the Brier score worsens by at most 2%. Otherwise that
target keeps its production model.

Why per target: on 2026-11-16 the new value-addition model was clearly better (PR-AUC
+0.022), but the new time-extension model was worse (−0.041). Contracts signed in 2023-H1,
which entered training for the first time, carry an unusual wave of time extensions in
territorial service contracts that did not repeat in 2024. An all-or-nothing gate would have
thrown away the better value-addition model.

### Election-calendar features and the first retrain after them

Since 2026-11-16 the models also get three election-calendar features
([`features/elections.py`](../src/procurement_risk/features/elections.py)). Each model
carries its own feature list, so the first monthly retrain afterwards compares the
production models (without these features) with new ones (with them) on the same rows, and
the per-target gate decides as usual. Election days follow the legal calendar up to 2040;
`test_calendar_covers_the_next_year` fails a year before that runs out.

## When a pipeline fails

Any failure opens an issue labelled `pipeline`, titled "Weekly refresh failed", "Monthly
retrain failed" or "Nightly snapshot failed". Later failures add comments to the same issue.
A failed run publishes nothing, so the site and the API keep their last good state.

The pipelines report their own failures. When the runner itself dies (out of memory, "lost
communication with the server") or a job hits its time limit, that step never runs, so
[`pipeline-watch.yml`](../.github/workflows/pipeline-watch.yml) reports it from a fresh
runner. A run you cancel by hand is not reported.

The most common cause is a **data-quality failure**. The run summary shows a table of
checks:

- **`processes row count`**: SECOP's tender dataset (`p6dx-8zbt`) is incomplete. This happened
  on 2026-11-15, when it was truncated to 1,000 rows. Wait for SECOP to restore it, then
  re-run the workflow (Actions → Weekly refresh → Run workflow).
- **`... vs previous`**: a dataset shrank by more than 5% since the last successful run.
  Check the dataset on datos.gov.co before re-running.
- **`contracts are recent`**: the newest contract is more than 14 days old. SECOP may have
  paused publishing.

Close the issue once a run succeeds.

## Reading `monitoring.json`

The weekly refresh writes [`web/public/data/monitoring.json`](../web/public/data/monitoring.json).
The website shows it under Methodology → Model health. It contains:

- `status`:
  - `ok`;
  - `watch`: an input shifted (PSI above 0.2), or realized ROC-AUC is 0.03 below the test
    ROC-AUC;
  - `insufficient_data`.
- `feature_drift`: PSI per input, comparing the last 90 days with the training period.
  Calendar inputs and history counts are marked `expected`, because they shift with the
  season and as the archive grows. They never trigger `watch`.
- `realized`: PR-AUC and ROC-AUC on contracts that closed after the model's training data
  ended and that have complete tender data. The `watch` alert uses ROC-AUC (0.03 below the
  test ROC-AUC), because PR-AUC rises with the base rate and that sample's base rate differs
  from the test period's.

A `watch` status does not mean the model is wrong. It is a prompt to look at the next
monthly retrain comparison.

## Running things by hand

Every workflow has a **Run workflow** button (`workflow_dispatch`) under the Actions tab, or
you can use the CLI:

```bash
gh workflow run weekly-refresh.yml
```

```bash
gh workflow run monthly-retrain.yml
```

Locally, the same steps are CLI commands. `PII_HASH_SALT` must be set for the downloads:

```bash
bash scripts/ingest_all.sh 2026-11-16
uv run python -m procurement_risk check-quality --raw data/raw
uv run python -m procurement_risk retrain --raw data/raw --bundle serving_bundle --as-of 2026-11-16
uv run python -m procurement_risk monitor --raw data/raw --bundle serving_bundle --as-of 2026-11-16
```

## One-time setup

- Repository secret `PII_HASH_SALT`, which is already set.
- Optional secret `SOCRATA_APP_TOKEN`, which avoids throttling by datos.gov.co.
- Settings → Actions → General → Workflow permissions: enable **"Allow GitHub Actions to
  create and approve pull requests"**, so the monthly retrain can open its pull request.
