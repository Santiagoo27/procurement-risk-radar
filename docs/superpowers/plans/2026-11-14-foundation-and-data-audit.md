# Foundation and Data Audit Implementation Plan (Phase 0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the public repo's foundation (PII-safe ingestion of SECOP II into Parquet, a nightly snapshot archive that cannot be backfilled later) and run the Phase 0 data audit that fixes the target and the feature whitelist for Phase 1.

**Architecture:** A Python package `procurement_risk` with a small Socrata client (keyset pagination, retries), an allowlist-based privacy layer that hashes natural-person suppliers, ingestion commands that write typed Parquet, a snapshot command run nightly by GitHub Actions that stores change-logs as GitHub Release assets, and DuckDB-based audit metrics rendered into `docs/data-audit.md`.

**Tech Stack:** Python ≥3.12, uv, httpx, pyarrow, duckdb, pytest, ruff, GitHub Actions, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-11-14-procurement-risk-design.md`

This plan covers spec §8 Phase 0 plus the Phase 1 snapshot archive (spec §11). Model training (rest of Phase 1) gets its own plan once the audit's decisions exist.

## Global Constraints

- Everything in the repo is in **English** (code, comments, README, docs, CLI help).
- Never use the words "corruption" or "fraud" to describe outputs; use "amendment risk signals". README carries the disclaimer: "Scores are statistical estimates for analysis, not allegations of wrongdoing."
- Free hosting only. No paid service, no always-on database.
- Dataset IDs on `https://www.datos.gov.co`: contracts `jbjy-vk9h`, amendments `cb9c-h8sn`, processes `p6dx-8zbt`.
- Personal data (spec §5.4) is never written to disk: columns are kept by **allowlist**, not denylist.
- Natural-person suppliers: name, document number and supplier code replaced by a salted SHA-256 hash; salt read from env `PII_HASH_SALT`, never committed.
- Leakage: nothing in this plan builds features; the audit only decides which columns are safe (spec §5.1).
- Raw and processed data live in `data/` and are git-ignored; only code, docs and small fixtures are committed.
- License: MIT for code. Data is SECOP open data; README credits Colombia Compra Eficiente / datos.gov.co.

## Review Focus

1. A supplier document type that is empty, misspelled or new (not exactly NIT): must be treated as a natural person and hashed (fail-safe). Test in Task 3.
2. `PII_HASH_SALT` missing or empty: ingestion must refuse to start, not write unhashed rows. Test in Task 3.
3. Socrata 429/5xx/timeout in the middle of pagination: retried with backoff; after retries are exhausted the command fails loudly, and the snapshot watermark does not advance. Tests in Tasks 2 and 5.
4. The same contract updated twice between runs, or appearing on two pages: snapshot change-log deduplicated on (`id_contrato`, `ultima_actualizacion`). Test in Task 5.
5. Socrata returns every field as a string, with nulls, `"No Definido"`, or odd date formats: parsed to typed columns, unparseable values become null instead of crashing. Test in Task 4.

---

## File Structure

```
pyproject.toml                         # uv project, deps, ruff + pytest config
README.md                              # English, disclaimer, data credit, status
LICENSE                                # MIT
.gitignore                             # data/, .venv/, __pycache__/, .env
.github/workflows/ci.yml               # ruff + pytest on push/PR
.github/workflows/snapshot.yml         # nightly snapshot to GitHub Release "snapshots"
src/procurement_risk/__init__.py
src/procurement_risk/__main__.py       # argparse CLI dispatch
src/procurement_risk/config.py         # dataset ids, column allowlists, paths
src/procurement_risk/sources/socrata.py# SocrataClient
src/procurement_risk/privacy.py        # supplier hashing, allowlist projection
src/procurement_risk/parsing.py        # string -> typed values
src/procurement_risk/ingest.py         # contracts / amendments / processes -> Parquet
src/procurement_risk/snapshot.py       # change-log snapshot + watermark
src/procurement_risk/audit/metrics.py  # DuckDB audit queries
src/procurement_risk/audit/text.py     # value-addition text matcher
src/procurement_risk/audit/report.py   # renders docs/data-audit.md
tests/...                              # mirrors src
tests/fixtures/                        # tiny hand-made Parquet/JSON fixtures
docs/data-audit.md                     # produced in Task 7
```

---

### Task 1: Project scaffold and CI

**Files:**
- Create: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`, `.github/workflows/ci.yml`, `src/procurement_risk/__init__.py`, `src/procurement_risk/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces in `config.py`:
  - `SOCRATA_DOMAIN = "www.datos.gov.co"`
  - `CONTRACTS_ID = "jbjy-vk9h"`, `AMENDMENTS_ID = "cb9c-h8sn"`, `PROCESSES_ID = "p6dx-8zbt"`
  - `CONTRACT_COLUMNS: tuple[str, ...]` allowlist: `id_contrato, proceso_de_compra, referencia_del_contrato, nombre_entidad, nit_entidad, codigo_entidad, departamento, ciudad, orden, sector, rama, entidad_centralizada, estado_contrato, codigo_de_categoria_principal, descripcion_del_proceso, objeto_del_contrato, tipo_de_contrato, modalidad_de_contratacion, justificacion_modalidad_de, fecha_de_firma, fecha_de_inicio_del_contrato, fecha_de_fin_del_contrato, duraci_n_del_contrato, el_contrato_puede_ser_prorrogado, tipodocproveedor, documento_proveedor, proveedor_adjudicado, codigo_proveedor, es_grupo, es_pyme, habilita_pago_adelantado, origen_de_los_recursos, destino_gasto, valor_del_contrato, valor_de_pago_adelantado, valor_facturado, valor_pagado, dias_adicionados, espostconflicto, liquidaci_n, ultima_actualizacion, urlproceso`
  - `AMENDMENT_COLUMNS = ("identificador", "id_contrato", "tipo", "descripcion", "fecharegistro")`
  - `PROCESS_COLUMNS` allowlist: `id_del_proceso, id_del_portafolio, referencia_del_proceso, nit_entidad, modalidad_de_contratacion, fecha_de_publicacion_del, precio_base, duracion, unidad_de_duracion, proveedores_invitados, proveedores_que_manifestaron, respuestas_al_procedimiento, proveedores_unicos_con, numero_de_lotes, estado_del_procedimiento, adjudicado, valor_total_adjudicacion, codigo_principal_de_categoria, tipo_de_contrato, subtipo_de_contrato`
  - `SNAPSHOT_COLUMNS = ("id_contrato", "valor_del_contrato", "fecha_de_fin_del_contrato", "dias_adicionados", "estado_contrato", "ultima_actualizacion")`
  - `DATA_DIR = Path("data")`

- [ ] **Step 1: Write the failing test** `tests/test_config.py`

```python
from procurement_risk import config

FORBIDDEN = {
    "nombre_representante_legal", "identificaci_n_representante_legal",
    "g_nero_representante_legal", "nombre_del_banco", "tipo_de_cuenta",
    "n_mero_de_cuenta", "nombre_supervisor", "n_mero_de_documento_supervisor",
    "nombre_ordenador_del_gasto", "n_mero_de_documento_ordenador_del_gasto",
    "nombre_ordenador_de_pago", "n_mero_de_documento_ordenador_de_pago",
    "direcci_n_de_ejecuci_n_del_contrato", "nombre_del_adjudicador",
    "nombre_del_proveedor", "nit_del_proveedor_adjudicado", "codigoproveedor",
}

def test_allowlists_exclude_personal_columns():
    for cols in (config.CONTRACT_COLUMNS, config.PROCESS_COLUMNS,
                 config.AMENDMENT_COLUMNS, config.SNAPSHOT_COLUMNS):
        assert FORBIDDEN.isdisjoint(cols)

def test_snapshot_columns_are_subset_of_contract_columns():
    assert set(config.SNAPSHOT_COLUMNS) <= set(config.CONTRACT_COLUMNS)
```

- [ ] **Step 2:** `uv run pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] **Step 3:** Create the uv project (`uv init --package --name procurement-risk`, then add `httpx pyarrow duckdb` and dev deps `pytest ruff`), `config.py` with the values above, MIT `LICENSE` (holder: the repo owner's GitHub name `Santiagoo27`), `.gitignore`, README (title, one-paragraph pitch, disclaimer from Global Constraints, data credit, "Status: Phase 0 — data audit"), and `ci.yml` running `uv sync`, `uv run ruff check .`, `uv run pytest` on ubuntu-latest.
- [ ] **Step 4:** `uv run pytest -v` → PASS; `uv run ruff check .` → no errors.
- [ ] **Step 5:** Commit `chore: scaffold project, config allowlists and CI`.

---

### Task 2: Socrata client

**Files:**
- Create: `src/procurement_risk/sources/__init__.py`, `src/procurement_risk/sources/socrata.py`, `tests/sources/test_socrata.py`

**Interfaces:**
- Produces: `class SocrataClient(domain: str = config.SOCRATA_DOMAIN, app_token: str | None = None, page_size: int = 50_000, max_retries: int = 5, transport: httpx.BaseTransport | None = None)`
  - `iter_pages(dataset_id: str, select: Sequence[str], where: str | None = None) -> Iterator[list[dict[str, str]]]` — keyset pagination: `$order=:id`, each next page adds `:id > '<last :id>'` to `where`; `:id` is requested via `$select` and stripped from yielded rows. Stops on an empty page.
  - Reads `SOCRATA_APP_TOKEN` from env when `app_token` is None; sends it as header `X-App-Token`.
  - Retries 429, 5xx and `httpx.TimeoutException` with exponential backoff (base 2 s, injectable `sleep` for tests); raises `SocrataError` after `max_retries`.
- Produces: `class SocrataError(RuntimeError)`.

- [ ] **Step 1: Write failing tests** using `httpx.MockTransport`:
  - `test_paginates_by_id_until_empty_page`: 3 responses (2 rows, 1 row, 0 rows) → yields 2 pages totalling 3 rows; the second request's `$where` contains `:id > 'row-2'`; yielded rows have no `:id` key.
  - `test_combines_user_where_with_keyset`: `where="fecha_de_firma >= '2021-01-01'"` → second request's `$where` is `(fecha_de_firma >= '2021-01-01') AND :id > '...'`.
  - `test_retries_429_then_succeeds`: responses 429, 503, 200 → returns data, `sleep` called twice.
  - `test_raises_after_max_retries`: always 500, `max_retries=3` → `SocrataError`.
  - `test_sends_app_token_header`.
- [ ] **Step 2:** `uv run pytest tests/sources -v` → FAIL.
- [ ] **Step 3:** Implement in `socrata.py`.
- [ ] **Step 4:** `uv run pytest tests/sources -v` → PASS.
- [ ] **Step 5:** Commit `feat: socrata client with keyset pagination and retries`.

---

### Task 3: Privacy layer

**Files:**
- Create: `src/procurement_risk/privacy.py`, `tests/test_privacy.py`

**Interfaces:**
- Produces:
  - `class MissingSaltError(RuntimeError)`
  - `load_salt(env: Mapping[str, str] = os.environ) -> bytes` — raises `MissingSaltError` if `PII_HASH_SALT` is absent or blank.
  - `is_natural_person(doc_type: str | None) -> bool` — `False` only when the normalized value (strip, upper, accents removed) equals `"NIT"`; everything else, including `None` and `""`, is `True`.
  - `hash_identifier(value: str | None, salt: bytes) -> str | None` — `None`/blank → `None`; else `"np_" + sha256(salt + value.strip().upper()).hexdigest()[:20]`.
  - `scrub_contract(row: Mapping[str, str], salt: bytes) -> dict[str, str | bool | None]` — projects onto `CONTRACT_COLUMNS` (missing keys → `None`), adds `supplier_is_natural_person: bool`; when natural, replaces `documento_proveedor` and `codigo_proveedor` with `hash_identifier(...)` and sets `proveedor_adjudicado` to `None`.
  - `project(row: Mapping[str, str], columns: Sequence[str]) -> dict[str, str | None]` — allowlist projection used for amendments, processes and snapshots.

- [ ] **Step 1: Write failing tests:**
  - `test_nit_is_company`: `"NIT"`, `" nit "` → `False`.
  - `test_unknown_or_empty_doc_type_is_natural_person` (Review Focus 1): `None`, `""`, `"Cédula de Ciudadanía"`, `"Pasaporte"`, `"NIT.."`, `"Otro"` → `True`.
  - `test_scrub_hashes_natural_person`: row with `tipodocproveedor="Cédula de Ciudadanía"`, `documento_proveedor="12345"`, `proveedor_adjudicado="JUAN PEREZ"`, plus `n_mero_de_cuenta="999"` → output has no `n_mero_de_cuenta` key, `proveedor_adjudicado is None`, `documento_proveedor.startswith("np_")`, `"12345"` and `"JUAN PEREZ"` appear in no output value, `supplier_is_natural_person is True`.
  - `test_scrub_keeps_company_supplier`: `tipodocproveedor="NIT"` → name and document unchanged.
  - `test_hash_is_stable_and_salted`: same input/salt → same hash; different salt → different hash.
  - `test_missing_salt_raises` (Review Focus 2): `{}` and `{"PII_HASH_SALT": "  "}` → `MissingSaltError`.
- [ ] **Step 2:** `uv run pytest tests/test_privacy.py -v` → FAIL.
- [ ] **Step 3:** Implement `privacy.py`.
- [ ] **Step 4:** `uv run pytest tests/test_privacy.py -v` → PASS.
- [ ] **Step 5:** Commit `feat: allowlist projection and salted hashing of natural-person suppliers`.

---

### Task 4: Typed parsing and ingestion to Parquet

**Files:**
- Create: `src/procurement_risk/parsing.py`, `src/procurement_risk/ingest.py`, `src/procurement_risk/__main__.py`, `tests/test_parsing.py`, `tests/test_ingest.py`

**Interfaces:**
- Consumes: `SocrataClient.iter_pages`, `privacy.load_salt`, `privacy.scrub_contract`, `privacy.project`, config allowlists.
- Produces in `parsing.py`:
  - `parse_money(v: str | None) -> float | None`, `parse_int(v) -> int | None`, `parse_bool(v) -> bool | None` (`"Si"/"Sí"/"true"/"1"` → True, `"No"/"false"/"0"` → False, else None), `parse_timestamp(v) -> datetime | None` (accepts Socrata floating timestamps `YYYY-MM-DDTHH:MM:SS(.fff)` and plain dates).
  - `MONEY_COLUMNS`, `INT_COLUMNS`, `BOOL_COLUMNS`, `TIMESTAMP_COLUMNS: frozenset[str]` covering the allowlisted columns of all three datasets.
  - `to_arrow(rows: list[dict], columns: Sequence[str]) -> pyarrow.Table` — applies the parser per column; everything else stays `string`.
- Produces in `ingest.py`:
  - `ingest_contracts(client, out_dir: Path, signed_from: date, signed_to: date, salt: bytes) -> Path` — `where = fecha_de_firma >= from AND fecha_de_firma < to`; writes `out_dir/contracts/part-00000.parquet, ...` one file per page; returns the directory.
  - `ingest_amendments(client, out_dir: Path) -> Path` — whole table, `AMENDMENT_COLUMNS`.
  - `ingest_processes(client, out_dir: Path, published_from: date, published_to: date) -> Path` — filters on `fecha_de_publicacion_del`.
- Produces CLI: `python -m procurement_risk ingest {contracts,amendments,processes} [--from YYYY-MM-DD --to YYYY-MM-DD] --out data/raw` (`--from`/`--to` required for contracts and processes, not accepted for amendments). `ingest contracts` calls `load_salt()` before the first request.

- [ ] **Step 1: Write failing tests:**
  - `test_parse_handles_garbage` (Review Focus 5): `parse_money("No Definido") is None`, `parse_money("1500000") == 1500000.0`, `parse_timestamp("2021-03-04T00:00:00.000") == datetime(2021,3,4)`, `parse_timestamp("31/12/2021") is None`, `parse_int(None) is None`, `parse_bool("Sí") is True`.
  - `test_to_arrow_types`: `valor_del_contrato` → float64, `fecha_de_firma` → timestamp, `dias_adicionados` → int64, unknown column → string.
  - `test_ingest_contracts_writes_scrubbed_parquet`: fake client yielding two pages incl. a natural-person row and an extra `n_mero_de_cuenta` key → parquet files read back have no `n_mero_de_cuenta` column, the natural person's raw document number appears nowhere, row count matches.
  - `test_ingest_contracts_requires_salt`: CLI with empty env → exits non-zero before any request (fake transport asserts no call).
- [ ] **Step 2:** `uv run pytest tests/test_parsing.py tests/test_ingest.py -v` → FAIL.
- [ ] **Step 3:** Implement `parsing.py`, `ingest.py`, `__main__.py`.
- [ ] **Step 4:** Tests → PASS; full suite `uv run pytest` → PASS.
- [ ] **Step 5:** Commit `feat: typed parsing and PII-safe ingestion to parquet`.

---

### Task 5: Nightly snapshot archive

**Files:**
- Create: `src/procurement_risk/snapshot.py`, `tests/test_snapshot.py`, `.github/workflows/snapshot.yml`
- Modify: `src/procurement_risk/__main__.py` (add `snapshot` command), `README.md` (section "Snapshot archive")

**Interfaces:**
- Consumes: `SocrataClient.iter_pages`, `privacy.project`, `parsing.to_arrow`, `config.SNAPSHOT_COLUMNS`.
- Produces:
  - `@dataclass Watermark(last_updated: datetime | None)` with `load(path: Path) -> Watermark` (missing file → `None` = full baseline) and `save(path: Path)` (JSON `{"last_updated": iso}`).
  - `take_snapshot(client, out_dir: Path, watermark: Watermark, run_date: date) -> tuple[Path | None, Watermark]` — `where = ultima_actualizacion > watermark` (no filter on baseline); writes `out_dir/changes-<run_date>.parquet` (or `baseline-<run_date>.parquet` when watermark is None), deduplicated on (`id_contrato`, `ultima_actualizacion`); returns `(None, watermark)` unchanged when there are no rows; new watermark = max `ultima_actualizacion` seen. Exceptions propagate; the watermark is only saved by the caller after a successful write.
  - CLI: `python -m procurement_risk snapshot --watermark data/snapshots/watermark.json --out data/snapshots`.
- Workflow `snapshot.yml`: `schedule: cron "0 7 * * *"` plus `workflow_dispatch`; `permissions: contents: write`; steps: checkout, setup uv, `gh release view snapshots || gh release create snapshots --title "Snapshot archive" --notes "Daily change-logs of SECOP II contract values and end dates."`, `gh release download snapshots -p watermark.json -D data/snapshots || true`, run the CLI with `SOCRATA_APP_TOKEN` from secrets, `gh release upload snapshots data/snapshots/*.parquet data/snapshots/watermark.json --clobber`. Upload happens only if the CLI step succeeded (default step semantics). `timeout-minutes: 300` (baseline is ~5.7M narrow rows).

- [ ] **Step 1: Write failing tests:**
  - `test_baseline_when_no_watermark`: no where-filter sent, file named `baseline-2026-11-15.parquet`.
  - `test_incremental_uses_watermark`: request `$where` contains `ultima_actualizacion > '2026-11-14T00:00:00'`.
  - `test_dedupes_same_contract_same_update` (Review Focus 4): two identical (id, ultima_actualizacion) rows across pages → 1 row; same id with two different update times → 2 rows.
  - `test_watermark_advances_to_max_seen`.
  - `test_failure_does_not_advance_watermark` (Review Focus 3): client raising `SocrataError` mid-pages → exception propagates, watermark file on disk unchanged, no parquet written.
  - `test_no_changes_returns_none`.
- [ ] **Step 2:** `uv run pytest tests/test_snapshot.py -v` → FAIL.
- [ ] **Step 3:** Implement `snapshot.py`, CLI command, workflow, README section.
- [ ] **Step 4:** Tests → PASS; run locally once against the live API with a short window to smoke-test: `uv run python -m procurement_risk snapshot --watermark data/snapshots/watermark.json --out data/snapshots` after writing a watermark of yesterday by hand → a `changes-*.parquet` with >0 rows and the 6 snapshot columns.
- [ ] **Step 5:** Commit `feat: nightly snapshot archive of contract values and end dates`.

---

### Task 6: Audit metrics

**Files:**
- Create: `src/procurement_risk/audit/__init__.py`, `src/procurement_risk/audit/text.py`, `src/procurement_risk/audit/metrics.py`, `tests/audit/test_text.py`, `tests/audit/test_metrics.py`, `tests/fixtures/audit/` (tiny Parquet built by a fixture function in the test file, not committed binaries)

**Interfaces:**
- Consumes: Parquet layout from Task 4 (`<raw>/contracts/*.parquet`, `<raw>/amendments/*.parquet`, `<raw>/processes/*.parquet`).
- Produces in `text.py`: `looks_like_value_addition(description: str | None) -> bool` — accent- and case-insensitive; True when the text mentions an addition of value (`adicion`/`adicionar`/`mayor valor` together with `valor`/`$`/`presupuesto`), False for `prorroga`/`plazo`-only texts, liquidation acts, empty text.
- Produces in `metrics.py` (each takes `con: duckdb.DuckDBPyConnection` with views `contracts`, `amendments`, `processes` created by `open_audit_db(raw_dir: Path) -> duckdb.DuckDBPyConnection`):
  - `label_rates_by_year(con) -> list[dict]` — keys `year, n_contracts, value_addition_rate, extension_rate`; value addition = contract has an amendment with `tipo = 'Adicion en el valor'`; extension = `dias_adicionados > 0`.
  - `hidden_value_additions(con) -> dict` — keys `explicit`, `hidden_matches` (rows with `tipo IN ('Modificacion General','No definido')` where `looks_like_value_addition(descripcion)`), `hidden_share = hidden_matches / (explicit + hidden_matches)`, `sample: list[str]` (50 random matched descriptions, seed 42).
  - `value_vs_award(con) -> dict` — joins `contracts.proceso_de_compra = processes.id_del_portafolio`; keys `join_rate`, `median_ratio_with_addition`, `median_ratio_without_addition` (ratio = `valor_del_contrato / valor_total_adjudicacion`).
  - `end_date_vs_duration(con) -> dict` — for contracts with `dias_adicionados > 0`: share whose `(fecha_de_fin - fecha_de_inicio)` in days exceeds the parsed original duration (`duraci_n_del_contrato`, e.g. `"30 Dia(s)"`, `"2 Mes(es)"`) by at least `0.8 * dias_adicionados`. Keys `n`, `share_end_date_moved`, `share_duration_unparseable`.
  - `closure_states(con, as_of: date) -> list[dict]` — per `estado_contrato`: `n`, `share_end_before_as_of_minus_180d`.
  - `bidder_coverage(con) -> dict` — non-null share of `proveedores_unicos_con` and `respuestas_al_procedimiento` among joined contracts, and share equal to 1.

- [ ] **Step 1: Write failing tests:**
  - `test_text_matcher`: True for `"ADICIÓN EN VALOR AL CONTRATO"`, `"adicionar $5.000.000 al contrato"`, `"Mayor valor del contrato"`; False for `"Prórroga en plazo"`, `"ACTA DE LIQUIDACION"`, `"Sin Descripción"`, `None`.
  - `test_label_rates_by_year`: fixture of 4 contracts in 2021 (1 with explicit addition, 2 with `dias_adicionados > 0`) → `value_addition_rate == 0.25`, `extension_rate == 0.5`.
  - `test_hidden_share`: fixture with 3 explicit and 1 hidden matching row → `hidden_share == 0.25`.
  - `test_value_vs_award_ratio`: fixture with ratios 1.5 (with addition) and 1.0 (without) → medians 1.5 and 1.0, `join_rate == 1.0`.
  - `test_end_date_vs_duration`: contract `"30 Dia(s)"`, start 2021-01-01, end 2021-03-02, `dias_adicionados=30` → counted as moved.
- [ ] **Step 2:** `uv run pytest tests/audit -v` → FAIL.
- [ ] **Step 3:** Implement `text.py`, `metrics.py` (register `looks_like_value_addition` as a DuckDB Python UDF).
- [ ] **Step 4:** `uv run pytest tests/audit -v` → PASS.
- [ ] **Step 5:** Commit `feat: data audit metrics`.

---

### Task 7: Run the audit and record decisions

**Files:**
- Create: `src/procurement_risk/audit/report.py`, `tests/audit/test_report.py`, `docs/data-audit.md`
- Modify: `src/procurement_risk/__main__.py` (add `audit` command), `README.md` (link the audit, update status)

**Interfaces:**
- Consumes: all functions of Task 6.
- Produces: `render_report(results: dict, decisions: dict) -> str` (Markdown) and CLI `python -m procurement_risk audit --raw data/raw --out docs/data-audit.md --as-of YYYY-MM-DD`, which writes metrics sections plus a "Decisions" section from the rules below.

Decision rules (spec §4, §10, §11):
- **Primary target:** if `hidden_share <= 0.30` → `has_value_addition` from `tipo = 'Adicion en el valor'`. If `> 0.30` and the manual precision check of `sample` (step 4) is ≥ 0.8 → text-recovered label (explicit OR hidden match). Otherwise → `has_time_extension` becomes primary. Record which branch was taken.
- **`valor_del_contrato`:** if `median_ratio_with_addition > 1.05` and `median_ratio_without_addition` is within [0.95, 1.05] → amended value: excluded from features; original value comes from `processes.valor_total_adjudicacion` (or `precio_base` if the award is missing). Otherwise → treated as original and allowed.
- **End date / duration:** if `share_end_date_moved > 0.5` → `fecha_de_fin_del_contrato` is post-amendment and excluded; original duration comes from `duraci_n_del_contrato` only if `end_date_vs_duration` shows it is not moved, else from `processes.duracion`.
- **Closed contract:** states whose `share_end_before_as_of_minus_180d` is ≥ 0.9, plus any contract whose end date is ≥ 180 days before `as_of`. Grace window = 180 days unless the data shows labels still arriving later (check `label_rates_by_year` trend for the last two years).
- **Bidders:** if non-null coverage ≥ 0.7 → `proveedores_unicos_con` joins the feature whitelist as `n_bidders` plus `single_bidder`.
- **Feature whitelist:** list every column from `CONTRACT_COLUMNS` and `PROCESS_COLUMNS` as allowed / excluded with a one-line reason (spec §5.1 list is excluded by default unless a rule above clears it).

- [ ] **Step 1: Write failing test** `test_render_report_contains_decisions`: given results with `hidden_share=0.1` → output contains `"Primary target: has_value_addition"`; with `hidden_share=0.5`, `sample_precision=0.5` → `"Primary target: has_time_extension"`.
- [ ] **Step 2:** `uv run pytest tests/audit/test_report.py -v` → FAIL; implement `report.py` and the CLI; → PASS.
- [ ] **Step 3: Pull the audit sample** (requires `PII_HASH_SALT` set locally, e.g. in `.env`, not committed):
  - `uv run python -m procurement_risk ingest contracts --from 2021-01-01 --to 2023-01-01 --out data/raw`
  - `uv run python -m procurement_risk ingest amendments --out data/raw`
  - `uv run python -m procurement_risk ingest processes --from 2020-07-01 --to 2023-01-01 --out data/raw`
  - First check contracts per signing year (`label_rates_by_year`); if 2021–2022 hold fewer than 200k contracts in total, widen to 2020–2023.
- [ ] **Step 4: Manual precision check:** read the 50 `sample` descriptions, mark each as a real value addition or not, record `sample_precision` in the report input.
- [ ] **Step 5:** `uv run python -m procurement_risk audit --raw data/raw --out docs/data-audit.md --as-of 2026-11-14`; read the output and confirm every spec §12 question has an answer and the Decisions section names the primary target, the closed-contract rule and the whitelist.
- [ ] **Step 6:** If the primary target is not `has_value_addition`, say so to the owner when reporting (spec §11: informed, not blocked).
- [ ] **Step 7:** Commit `docs: phase 0 data audit and target decisions`.

---

### Task 8: Publish the repo and start the archive

Outward-facing: each step that creates or changes something on GitHub needs the owner's explicit yes in chat first.

**Run this task right after Task 5, before Tasks 6–7.** The snapshot archive cannot be backfilled, so every day it starts earlier is data kept. Tasks 6–7 then push to the already-public repo.

- [ ] **Step 1:** Ask the owner to confirm the public repo name (proposal `procurement-risk-radar`) and that it may be created as public under `Santiagoo27`.
- [ ] **Step 2:** `gh repo create Santiagoo27/<name> --public --source . --push --description "Predicting, at signing time, which public contracts will be amended. End-to-end ML on Colombia's SECOP II open data."`
- [ ] **Step 3:** The owner sets the secrets themselves (values never pass through chat): `gh secret set PII_HASH_SALT` (a random value they generate) and optionally `gh secret set SOCRATA_APP_TOKEN` (free token from datos.gov.co).
- [ ] **Step 4:** `gh workflow run snapshot.yml`, then `gh run watch` → success; `gh release view snapshots` lists `baseline-*.parquet` and `watermark.json`.
- [ ] **Step 5:** Confirm CI is green on `main` (`gh run list --workflow ci.yml --limit 1` → completed/success).
