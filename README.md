# Procurement Risk Radar

Predicting, **at signing time**, which public contracts will later be amended (value
additions and time extensions). An end-to-end machine learning system built on Colombia's
SECOP II open procurement data, designed around the
[Open Contracting Data Standard](https://standard.open-contracting.org/) so other
countries can be added.

> **Disclaimer.** Scores are statistical estimates for analysis, not allegations of
> wrongdoing. This project reports amendment risk signals; it does not detect or claim
> corruption or fraud.

**Status:** Phase 0 — data audit.

## Data

Source: SECOP II open data published by Colombia Compra Eficiente on
[datos.gov.co](https://www.datos.gov.co): contracts (`jbjy-vk9h`), contract amendments
(`cb9c-h8sn`) and procurement processes (`p6dx-8zbt`).

Privacy: only an allowlist of columns is ever stored. Personal data in the source
(legal representatives, supervisors, bank accounts) is never written to disk, and
suppliers who are natural persons are replaced by a salted hash.

## Snapshot archive

SECOP publishes *that* a contract received a value addition, but not *how much*. To be able
to measure amendment size later, a nightly GitHub Actions job
([`snapshot.yml`](.github/workflows/snapshot.yml)) records every contract whose
`ultima_actualizacion` changed since the previous run: contract value, end date, added
days and status. Files are attached to the
[`snapshots` release](../../releases/tag/snapshots): `baseline-YYYY-MM-DD.parquet` (full
download, also re-taken on the first day of each month) and `changes-YYYY-MM-DD.parquet`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

## License

Code: MIT, see [LICENSE](LICENSE).
