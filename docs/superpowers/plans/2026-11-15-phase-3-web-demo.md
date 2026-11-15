# Phase 3: Web Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Before writing any chart, map colour scale or legend code, load the `dataviz` skill.

**Goal:** Publish a public web demo that anyone can understand in 30 seconds. It has five parts:
- An interactive map of Colombia with observed amendment rates by department and municipality.
- A predicted-risk layer for contracts that are still open.
- Entity pages listing each buyer's riskiest open contracts.
- A "try it" form that scores a hypothetical contract through the live API.
- A methodology page that carries the disclaimer.

**Architecture:** The Python package gains an `export-web-data` step. It writes small, privacy-safe static JSON files: national summary, department and municipality aggregates, an entity index, and entity details sharded by department. It also writes a TopoJSON of municipal boundaries. Those files live in `web/public/` and a static React + TypeScript (Vite) app reads them. The app renders the map as SVG with `d3-geo` (no tile provider, no tokens) and calls the Render API only for the "try it" form. Vercel hosts the app from `web/`.

**Tech Stack:** Python (DuckDB, existing pipeline), Node 24, Vite, React, TypeScript, React Router, Tailwind CSS, d3-geo, d3-scale, d3-zoom, topojson-client, Vitest + Testing Library, mapshaper (build-time only), Vercel.

**Spec:** `docs/superpowers/specs/2026-11-14-procurement-risk-design.md`. The relevant sections are §2 (anti-goals: no accusatory framing, no supplier rankings), §8 Phase 3, and §10 (map default: observed value-addition rate on closed contracts; selector to time extension and to a predicted layer for open contracts, labelled as an estimate).

## Global Constraints

- English UI. The footer of every page carries the disclaimer "Scores are statistical estimates for analysis, not allegations of wrongdoing." Never the words "corruption" or "fraud".
- **Privacy:** no supplier names, supplier identifiers, natural-person data or free text (`objeto_del_contrato`, `descripcion_*`, amendment text) in any web data file. Contract rows show only `id_contrato`, the public SECOP URL, signing date, contract type, procurement method, awarded value, planned duration, risk, percentile and top signals.
- **No rankings of suppliers.** Rankings of buyers by observed rate are allowed only with the sample size shown and only above the minimum sample.
- **Minimum sample:** a region or entity with fewer than 30 closed contracts in the period shows "not enough data", never a rate.
- Regions are assigned by the **buyer's** department and municipality (where the entity is registered, not where the work happens). The methodology page says so.
- **Observed period:** closed contracts signed 2022-01-01 to 2024-12-31. **Predicted layer:** open contracts as of the export date (2026-11-14), scored by the same models and feature SQL as the API.
- Free hosting only (Vercel Hobby). There is no backend besides the existing Render API (`https://procurement-risk-radar-9p25.onrender.com`), which may need about 1 minute to wake.
- Boundary data must allow redistribution with attribution. The attribution is shown in the footer.
- Pin exact npm versions with a committed `package-lock.json`.

## Review Focus

1. **SECOP names that don't match the boundary names** (accents, "Bogotá D.C." variants, "San Andrés…", duplicated municipality names in different departments) silently drop regions from the map. Expected: an export-time coverage report with at least 98% of contracts matched to a department and at least 95% to a municipality, and a test for the known variants. Owned by Task 1.
2. **Tiny samples** show 0% or 100% rates. Expected: suppression below 30 closed contracts. Test in Task 2.
3. **The API is asleep or down** while someone uses "try it". Expected: a visible "waking up the model (up to a minute)" state, a 90-second timeout, a retry button, never a blank or frozen page. Test in Task 6.
4. **Privacy leak through web data.** Expected: a test that scans every exported JSON for forbidden keys and for any value equal to a supplier name or document in the fixture. Test in Task 2.
5. **Mobile (375 px wide).** Expected: the map fits with no horizontal scroll, panels stack, the form is usable. Checked in the browser preview in Tasks 4–6.

---

## File Structure

```
src/procurement_risk/web/__init__.py
src/procurement_risk/web/geo.py            # name normalisation, DIVIPOLA/name matching, coverage report
src/procurement_risk/web/export.py         # export_web_data(): aggregates, entities, open-contract scores
tests/web/test_geo.py, tests/web/test_export.py
scripts/build_geo.sh                        # one-off: download boundaries, simplify with mapshaper -> TopoJSON
web/                                        # Vite + React + TS app
  package.json, package-lock.json, vite.config.ts, tsconfig.json, vercel.json, index.html
  public/geo/colombia-municipalities.topo.json     # committed (small, attributed)
  public/data/{summary,departments,municipalities,entities}.json
  public/data/entities/<department-slug>.json      # entity details + top open contracts
  src/main.tsx, src/App.tsx, src/routes/*.tsx
  src/lib/{data.ts,api.ts,scale.ts,format.ts}
  src/components/{Map.tsx,Legend.tsx,LayerPicker.tsx,RegionPanel.tsx,RiskBadge.tsx,Signals.tsx,Disclaimer.tsx}
  src/**/*.test.ts(x)
.github/workflows/ci.yml                    # job `web`: npm ci, typecheck, test, build
```

---

### Task 1: Boundaries and name matching

**Files:**
- Create: `scripts/build_geo.sh`, `web/public/geo/colombia-municipalities.topo.json`, `src/procurement_risk/web/__init__.py`, `src/procurement_risk/web/geo.py`, `tests/web/__init__.py`, `tests/web/test_geo.py`, `docs/geo-sources.md`

**Source decision (first step, recorded in `docs/geo-sources.md`):**
- Preferred source: **DANE Marco Geoestadístico Nacional** municipal layer. It includes DIVIPOLA codes and department attributes. Confirm that its terms allow redistribution with attribution.
- Fallback: **geoBoundaries gbOpen COL ADM2** (DANE source, CC BY 4.0, 1,122 units). It has no department attribute. Departments are then assigned from SECOP's own (department, municipality) pairs plus a manual table for ambiguous names.
- Do not use geoBoundaries ADM1. It comes from OpenStreetMap (ODbL) and its borders don't match ADM2.
- **Department shapes are dissolved from the municipal layer** with mapshaper, so both levels share borders.
- Note: GitHub serves geoBoundaries files through Git LFS. Download via the geoBoundaries API's `simplifiedGeometryGeoJSON` link resolved through `media.githubusercontent.com`, or the release zip.

**Interfaces:**
- `scripts/build_geo.sh`:
  - Downloads the chosen source to `data/geo/` (git-ignored).
  - Runs `npx mapshaper@<pinned> -simplify 8% keep-shapes -o format=topojson` with two objects: `municipalities` (properties `mpio_code`, `mpio_name`, `dpto_code`, `dpto_name`) and `departments` (dissolved by `dpto_code`).
  - Writes `web/public/geo/colombia-municipalities.topo.json`. Target size ≤ 800 KB.
- `geo.normalize_name(name: str | None) -> str | None`: casefold, strip accents, collapse whitespace, drop punctuation and the words `d.c.`, `distrito capital`, `de`, `del`.
- `geo.load_regions(topo_path: Path) -> pandas.DataFrame` with columns `dpto_code, dpto_name, mpio_code, mpio_name, dpto_key, mpio_key` (normalised keys).
- `geo.match_regions(pairs: pandas.DataFrame[department, city], regions) -> pandas.DataFrame` adding `dpto_code, mpio_code`. Uses the manual `ALIASES: dict[str, str]` for known variants. Unmatched rows keep null codes.
- `geo.coverage(matched, weights) -> dict(department_share, municipality_share, unmatched_top: list[(department, city, n)])`.

- [ ] **Step 1:** Decide the source and record it in `docs/geo-sources.md` (source, URL, license, date, attribution text). Then run `bash scripts/build_geo.sh`. The TopoJSON should exist, be ≤ 800 KB and hold 33 departments and about 1,120 municipalities.
- [ ] **Step 2: Write failing tests:**
  - `test_normalize_variants`: `"Bogotá D.C."`, `"Bogotá, D.C."`, `"Distrito Capital de Bogotá"` → the same key. Also `"San Andrés, Providencia y Santa Catalina"` matches the boundary's archipelago name.
  - `test_duplicate_municipality_names_resolved_by_department`: `("Antioquia", "La Unión")` and `("Nariño", "La Unión")` → different `mpio_code`s.
  - `test_coverage_reports_unmatched`.
- [ ] **Step 3:** `uv run pytest tests/web/test_geo.py -v` → FAIL; implement `geo.py` → PASS.
- [ ] **Step 4:** Run `match_regions` on the real `(departamento, ciudad)` pairs weighted by contract counts. Add aliases until `department_share ≥ 0.98` and `municipality_share ≥ 0.95`, and record the final numbers in `docs/geo-sources.md`. City values like `No Definido` stay unmatched at municipality level but count toward the department.
- [ ] **Step 5:** Commit `feat: municipal and departmental boundaries with SECOP name matching`.

---

### Task 2: Web data export

**Files:**
- Create: `src/procurement_risk/web/export.py`, `tests/web/test_export.py`
- Modify: `src/procurement_risk/__main__.py` (command `export-web-data`)

**Interfaces:**
- Consumes:
  - the raw data;
  - `build_canonical`, `build_labels`, `build_history` and `feature_frame` (same features as training and serving);
  - models from `data/models/<target>/model.joblib`;
  - `geo.match_regions`;
  - the bundle's `score_quantiles` for percentiles (`serving_bundle/metadata.json`).
- Produces `export_web_data(raw_dir, models_dir, bundle_dir, topo_path, out_dir, as_of, observed_from=date(2022,1,1), observed_to=date(2025,1,1), min_n=30) -> dict`, which returns the coverage report and the file sizes. It writes:
  - `summary.json`: `{as_of, observed_period, n_closed, n_open_scored, national: {value_addition_rate, extension_rate}, model_metrics, coverage}`.
  - `departments.json` and `municipalities.json`: one row per code with `name`, `n_closed`, `value_addition_rate`, `extension_rate` (null when `n_closed < min_n`), `n_open`, `predicted_value_addition` and `predicted_extension` (mean calibrated probability over open contracts; null when `n_open < min_n`).
  - `entities.json`: `[{buyer_id, name, dpto_code, mpio_code, n_closed, value_addition_rate, extension_rate, n_open}]` with the same suppression.
  - `entities/<dpto-slug>.json`: `{buyer_id: {top_open: [≤ 10 contracts by predicted value-addition probability]}}`. Each contract has `id_contrato, url, signed_at, contract_type, procurement_method, award_value, planned_duration_days, value_addition: {probability, percentile, top_signals}, time_extension: {...}`. The signals use `serving.labels.FEATURE_LABELS` and the same `provided` flag as the API.
  - Open contracts: canonical contracts that are not closed at `as_of` and were signed within the 2 years before `as_of`.
  - `url` comes from `urlproceso` (stored as a dict string by Phase 0; unwrap `{'url': ...}`).
- CLI:

  ```
  python -m procurement_risk export-web-data --raw data/raw --models data/models \
    --bundle serving_bundle --topo web/public/geo/colombia-municipalities.topo.json \
    --out web/public/data --as-of 2026-11-14
  ```

- [ ] **Step 1: Write failing tests** (with the `make_raw` fixture, a tiny topo built in the test, and the demo models):
  - `test_rates_suppressed_below_min_n` (Review Focus 2).
  - `test_department_rate_matches_hand_count`.
  - `test_open_contracts_scored_with_shared_features`: the probability for one open contract equals `RiskModel.predict_proba` on `feature_frame` for that contract.
  - `test_web_data_has_no_private_fields` (Review Focus 4): walk every output file and assert no key in `{"proveedor_adjudicado", "documento_proveedor", "codigo_proveedor", "supplier_key", "objeto_del_contrato", "descripcion_del_proceso", "descripcion"}`, and that no string value equals a supplier name or document from the fixture.
  - `test_urlproceso_unwrapped`.
- [ ] **Step 2:** `uv run pytest tests/web -v` → FAIL; implement; → PASS.
- [ ] **Step 3: Real data.** Ingest recent contracts and processes first, because open contracts need 2025–2026 signings:
  - `ingest contracts --from 2025-01-01 --to 2026-11-15 --out data/raw_recent`
  - `ingest processes --from 2024-07-01 --to 2026-11-15 --out data/raw_recent`
  - Ruling for the executor: either merge `data/raw` and `data/raw_recent` into one directory for the export, or make `open_audit_db` accept several roots. Pick the smaller change and ledger it.

  Then run `export-web-data`. Check the size of each file (`entities/<dpto>.json` ≤ 600 KB, everything else ≤ 300 KB, total ≤ 8 MB), that coverage meets the Task 1 thresholds, and that `n_open_scored > 0`.
- [ ] **Step 4:** Commit `feat: privacy-safe static web data export` (code only), then commit the generated `web/public/data` separately as `data: web aggregates as of 2026-11-14`.

---

### Task 3: Web app scaffold and CI

**Files:**
- Create: `web/` (Vite React-TS template), `web/vercel.json` (SPA rewrite to `/index.html`), `web/src/App.tsx` with routes `/`, `/entity/:buyerId`, `/try`, `/methodology`, `web/src/components/Disclaimer.tsx`, `web/src/lib/data.ts`, `web/src/lib/format.ts`
- Modify: `.github/workflows/ci.yml` (job `web`: `actions/setup-node@v4` with `node-version: 24`, `cache: npm`, `working-directory: web`; `npm ci`, `npm run typecheck`, `npm test -- --run`, `npm run build`), `.gitignore` (`web/node_modules/`, `web/dist/`), `README.md` (development section)

**Interfaces:**
- `data.ts`: typed loaders `loadSummary()`, `loadDepartments()`, `loadMunicipalities()`, `loadEntities()`, `loadEntityDetails(dptoSlug)` and `loadTopology()`. They are cached and throw `DataError` with a readable message.
- `format.ts`:
  - `pct(x: number | null) -> "12.3%" | "not enough data"`
  - `cop(x) -> "$40.0M COP"` (compact)
  - `days(x)`
  - `date(iso)`
- Layout: a header with the project name and nav (Map · Try it · Methodology · GitHub), and the footer `Disclaimer` with the data and boundary attributions.

- [ ] **Step 1: Write failing tests** `format.test.ts` (null → "not enough data", compact COP, percent rounding) and `data.test.ts` (a mocked `fetch` failure throws `DataError`).
- [ ] **Step 2:** Scaffold with `npm create vite@<pinned> web -- --template react-ts`, add the dependencies at exact versions, then `npm test -- --run` → FAIL; implement → PASS; `npm run build` → success.
- [ ] **Step 3:** Commit `feat: web app scaffold with data loaders and CI`.

---

### Task 4: Map and home page

**Files:**
- Create: `web/src/components/{Map.tsx,Legend.tsx,LayerPicker.tsx,RegionPanel.tsx}`, `web/src/lib/scale.ts`, `web/src/routes/Home.tsx`, tests next to them

**Interfaces:**
- `scale.ts`:
  - `LAYERS = [{id: "observed_value_addition", label: "Value additions (observed)", field: "value_addition_rate"}, {id: "observed_extension", ...}, {id: "predicted_value_addition", label: "Predicted risk, open contracts (estimate)", field: "predicted_value_addition"}]`.
  - `colorScale(values: (number|null)[]) -> (v: number|null) => string`: sequential quantile scale in 5 bins, colour-blind-safe palette from the `dataviz` skill, grey for null.
  - `legendBins(scale)`.
- `Map.tsx`:
  - SVG with `geoMercator().fitSize` on Colombia and pan/zoom via `d3-zoom`.
  - The default level is departments. Clicking a department zooms in and shows its municipalities.
  - Hover or tap shows a tooltip with name, rate and `n`.
  - Keyboard focusable regions with `aria-label`.
- `RegionPanel.tsx`:
  - The selected region's numbers against the national figure.
  - The top 10 buyers in that region by the active layer's rate (only `n_closed ≥ 30`), each linking to its entity page, with `n` shown.
- `Home.tsx`:
  - A one-sentence pitch.
  - Three headline numbers from `summary.json`.
  - `LayerPicker`, `Map`, `Legend` and `RegionPanel`.
  - The predicted layer shows an "Estimate" badge and a one-line explanation.

- [ ] **Step 1: Write failing tests:** `scale.test.ts` (null → grey, bins are monotonic, 5 legend entries), `RegionPanel.test.tsx` (buyers below the minimum sample are excluded and each row shows `n`), and `Legend.test.tsx`.
- [ ] **Step 2:** Implement → `npm test -- --run` PASS, `npm run typecheck` clean.
- [ ] **Step 3: Visual check.** Run `npm run dev` with the browser preview (`.claude/launch.json` entry `web`, port 5173) and take screenshots of:
  - the department view;
  - a drill-down into Antioquia;
  - each of the 3 layers;
  - the mobile preset (375 px, Review Focus 5).

  Fix any layout or overflow problems found. **Then show the owner the screenshots and get their reaction to the look before Task 5** (colours, density, wording).
- [ ] **Step 4:** Commit `feat: interactive map with observed and predicted layers`.

---

### Task 5: Entity page

**Files:**
- Create: `web/src/routes/Entity.tsx`, `web/src/components/{RiskBadge.tsx,Signals.tsx}`, tests

**Interfaces:**
- `Entity.tsx` loads `entities.json` and the department shard and shows:
  - name, department and municipality;
  - observed rates against the national rate, with `n`;
  - a table of the top open contracts: id linking to SECOP, signing date, type, method, value, duration, `RiskBadge` for both targets (probability and percentile), and `Signals` with "(not provided)" wording;
  - a link to "Try a similar contract", which pre-fills the form with the entity.
- An unknown `buyerId` shows a not-found message with a link back to the map.

- [ ] **Step 1: Write failing tests:** `Entity.test.tsx` (renders rates and the contracts table from fixture JSON; unknown id → not-found) and `RiskBadge.test.tsx` (the percentile text and colour band).
- [ ] **Step 2:** Implement → PASS. Visual check on desktop and mobile.
- [ ] **Step 3:** Commit `feat: entity pages with riskiest open contracts`.

---

### Task 6: "Try it" form

**Files:**
- Create: `web/src/lib/api.ts`, `web/src/routes/Try.tsx`, tests

**Interfaces:**
- `api.ts`:
  - `API_URL` from `import.meta.env.VITE_API_URL`, defaulting to the Render URL.
  - `searchBuyers(q)`.
  - `predict(contract, {signal})` with a 90-second timeout via `AbortController`.
  - `wakeUp()` calls `/health` and is fired on page load.
  - Errors are typed: `ApiTimeout`, `ApiUnavailable`, `ApiValidation(detail)`, `UnknownBuyer`.
- `Try.tsx`:
  - A buyer search with debounced autocomplete against `/buyers`, plus a form for the main fields with client-side limits matching the API (dates 2000–2100, values ≥ 0 and ≤ 1e15, duration 1–3650).
  - While the API wakes it shows "Waking up the model — the free server sleeps when idle (up to a minute)".
  - Results show both targets with probability, percentile and signals, plus the disclaimer.
  - Errors show a message and a Retry button.

- [ ] **Step 1: Write failing tests** with a mocked `fetch`:
  - `test shows waking state until health responds`;
  - `test timeout shows retry` (Review Focus 3);
  - `test validation errors are shown per field`;
  - `test renders result with signals and not-provided wording`.
- [ ] **Step 2:** Implement → PASS. Run a manual end-to-end check against the live API in the preview: search "medellin distrito", score a contract, and see the result.
- [ ] **Step 3:** Commit `feat: try-it form backed by the live API`.

---

### Task 7: Methodology, deploy and README

**Files:**
- Create: `web/src/routes/Methodology.tsx`
- Modify: `README.md`, `docs/api.md`

**Methodology content** (in plain language):
- What the score means and what it doesn't.
- The data source and periods.
- How labels are built, including the 71% of hidden additions and the 84% precision.
- The no-leakage design.
- Model metrics from `summary.json`.
- The region assignment by buyer.
- The minimum sample.
- The privacy choices.
- Links to the data audit, model card, API docs and repo.

**Steps:**

- [ ] **Step 1:** Implement the page and test that it renders the metrics from `summary.json`. Then run `npm run build` and commit `feat: methodology page`.
- [ ] **Step 2 (owner OK required):** push to `main` and confirm CI is green (`test`, `docker-smoke`, `render-image-smoke`, `web`).
- [ ] **Step 3 (owner action):** in Vercel, the owner imports the GitHub repo with these settings:
  - Root Directory `web`, Framework Preset Vite, Build Command `npm run build`, Output `dist`.
  - Environment variable `VITE_API_URL=https://procurement-risk-radar-9p25.onrender.com`.

  The executor gives these exact settings, then verifies the deployed URL: map renders, entity page loads, "try it" returns a score.
- [ ] **Step 4:** Restrict API CORS to the Vercel domain: set `ALLOWED_ORIGINS` in `render.yaml` to the Vercel URL plus `http://localhost:5173`, and redeploy.
- [ ] **Step 5:** Update the README:
  - the live demo link at the top;
  - a screenshot of the map at `docs/figures/web-map.png`, taken from the preview;
  - status → Phase 3 complete.

  Commit, then push after the owner's OK.
