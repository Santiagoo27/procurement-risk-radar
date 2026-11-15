"""Build web/public/geo/colombia-municipalities.topo.json.

Sources (see docs/geo-sources.md):
- Municipal polygons: geoBoundaries gbOpen COL ADM2, simplified (DANE source, CC BY 4.0).
  They carry only a name, so...
- ...official codes come from DANE's DIVIPOLA table on datos.gov.co (gdxc-w37w,
  CC BY-SA 4.0), whose point coordinates are joined to the polygons (point in polygon).
Departments are dissolved from municipalities so both levels share borders.

Usage:
    uv run python scripts/build_geo.py --adm2 path/to/geoBoundaries-COL-ADM2_simplified.geojson
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import httpx
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

DIVIPOLA_URL = "https://www.datos.gov.co/resource/gdxc-w37w.json?$limit=5000"
MAPSHAPER = "mapshaper@0.7.101"


def load_divipola() -> list[dict]:
    rows = httpx.get(DIVIPOLA_URL, timeout=60).json()
    for r in rows:
        r["lon"] = float(r["longitud"].replace(",", "."))
        r["lat"] = float(r["latitud"].replace(",", "."))
    return rows


def assign_codes(features: list[dict], divipola: list[dict]) -> tuple[list[dict], dict]:
    polys = [shape(f["geometry"]) for f in features]
    tree = STRtree(polys)
    owner: dict[int, dict] = {}
    report = {"points": len(divipola), "inside": 0, "nearest": 0, "conflicts": []}
    for row in divipola:
        point = Point(row["lon"], row["lat"])
        hits = [i for i in tree.query(point) if polys[i].contains(point)]
        if hits:
            idx = int(hits[0])
            report["inside"] += 1
        else:
            idx = int(tree.nearest(point))
            report["nearest"] += 1
        if idx in owner:
            report["conflicts"].append((owner[idx]["cod_mpio"], row["cod_mpio"]))
            continue
        owner[idx] = row
    out = []
    for i, feature in enumerate(features):
        row = owner.get(i)
        if row is None:
            continue
        out.append({
            "type": "Feature",
            "geometry": feature["geometry"],
            "properties": {"mpio_code": row["cod_mpio"], "mpio_name": row["nom_mpio"].title(),
                           "dpto_code": row["cod_dpto"], "dpto_name": row["dpto"].title()},
        })
    report["polygons"] = len(features)
    report["assigned"] = len(out)
    report["unassigned_polygons"] = len(features) - len(out)
    return out, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adm2", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=Path("web/public/geo/colombia-municipalities.topo.json"))
    parser.add_argument("--simplify", default="8%")
    args = parser.parse_args()

    raw = json.loads(args.adm2.read_bytes().decode("utf-8", errors="replace"))
    features, report = assign_codes(raw["features"], load_divipola())
    print(json.dumps({k: v for k, v in report.items() if k != "conflicts"}, indent=2))
    print("conflicts:", report["conflicts"][:20], len(report["conflicts"]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "municipalities.geojson"
        src.write_text(json.dumps({"type": "FeatureCollection", "features": features}),
                       encoding="utf-8")
        cmd = (
            f'npx --yes {MAPSHAPER} -i "{src}" name=municipalities '
            f"-simplify {args.simplify} keep-shapes "
            "-dissolve dpto_code copy-fields=dpto_name + name=departments "
            f'-o format=topojson quantization=1e5 target=* "{args.out}"'
        )
        subprocess.run(cmd, shell=True, check=True)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
