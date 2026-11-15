# Geographic sources

`web/public/geo/colombia-municipalities.topo.json` is built by `scripts/build_geo.py`. It
holds two objects: `municipalities` (1,120) and `departments` (33). The departments are
dissolved from the municipalities, so both levels share borders.

| Source | What it provides | License |
|---|---|---|
| [geoBoundaries gbOpen COL ADM2](https://www.geoboundaries.org/) (simplified, build 2023-12-12; original source DANE, 2020) | Municipal polygons (name only) | CC BY 4.0 |
| [DANE DIVIPOLA – Códigos municipios](https://www.datos.gov.co/d/gdxc-w37w) (datos.gov.co `gdxc-w37w`) | Official municipal and department codes and names, plus point coordinates | CC BY-SA 4.0 |

**How codes are assigned.** Each DIVIPOLA point is placed in the polygon that contains it.
All 1,122 points fell inside a polygon. In two cases two points fell in the same polygon,
because the polygons predate recent boundary changes:

- `27493` Nuevo Belén de Bajirá falls in the polygon of `27615` Riosucio.
- `13440` Margarita falls in the polygon of `47318` Guamal.

The first point to land keeps the polygon, so two polygons stay unassigned. Contracts in
those two municipalities still count toward their department.

**Processing.** Polygons are simplified to 8% with `mapshaper@0.7.101` (`keep-shapes`),
dissolved by department code, and exported as TopoJSON.

**Attribution.** Displayed on the site: "Boundaries: geoBoundaries (CC BY 4.0) and DANE
DIVIPOLA (CC BY-SA 4.0)". The derived TopoJSON is shared under CC BY-SA 4.0.

## Name matching coverage

Names follow the spelling of each source. SECOP buyer names are matched to these regions
by `procurement_risk.web.geo`; the coverage on real data is recorded below.

Measured on 3,468,109 SECOP II contracts signed 2019–2024:

| Level | Share of contracts matched |
|---|---:|
| Department | 98.3% (the remaining 1.7% have `departamento = No Definido`) |
| Municipality, all contracts | 92.2% |
| Municipality, contracts with a defined city | 99.99% |

About 6% of contracts have `ciudad = No Definido`. These are mostly department-level
entities, such as gobernaciones, so they appear in the department layer only. Bogotá is a
one-municipality department, so its contracts are placed even without a city.

Matching rules:

- Names are normalised: accents, case and punctuation removed, and tokens such as "D.C."
  and "Archipiélago" dropped.
- A short name matches a unique official long name by whole-word prefix or suffix, for
  example "Cali" → "Santiago De Cali".
- A few spellings are set by hand in `ALIASES`, for example "Don Matías" → "Donmatías".
