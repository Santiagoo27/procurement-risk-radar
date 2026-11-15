import json

import pandas as pd
import pytest

from procurement_risk.web.geo import coverage, load_regions, match_regions, normalize_name


@pytest.fixture
def topo(tmp_path):
    def mpio(code, name, dcode, dname):
        return {"type": "Polygon", "arcs": [],
                "properties": {"mpio_code": code, "mpio_name": name,
                               "dpto_code": dcode, "dpto_name": dname}}
    data = {"type": "Topology", "arcs": [], "objects": {
        "municipalities": {"type": "GeometryCollection", "geometries": [
            mpio("11001", "Bogotá, D.C.", "11", "Bogotá, D.C."),
            mpio("05400", "La Unión", "05", "Antioquia"),
            mpio("52399", "La Unión", "52", "Nariño"),
            mpio("88001", "San Andrés", "88",
                 "Archipiélago De San Andrés, Providencia Y Santa Catalina"),
            mpio("05001", "Medellín", "05", "Antioquia"),
            mpio("76001", "Santiago De Cali", "76", "Valle Del Cauca"),
            mpio("76520", "Palmira", "76", "Valle Del Cauca"),
        ]},
        "departments": {"type": "GeometryCollection", "geometries": []},
    }}
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("a,b", [
    ("Bogotá D.C.", "Bogotá, D.C."),
    ("Distrito Capital de Bogotá", "Bogotá, D.C."),
    ("San Andrés, Providencia y Santa Catalina",
     "Archipiélago De San Andrés, Providencia Y Santa Catalina"),
    ("  MEDELLÍN ", "Medellín"),
    ("Valle del Cauca", "Valle Del Cauca"),
])
def test_normalize_variants(a, b):
    assert normalize_name(a) == normalize_name(b)


def test_normalize_keeps_distinct_names_distinct():
    assert normalize_name("La Unión") != normalize_name("Unión Panamericana")
    assert normalize_name(None) is None
    assert normalize_name("No Definido") is None


def test_duplicate_municipality_names_resolved_by_department(topo):
    regions = load_regions(topo)
    pairs = pd.DataFrame({"department": ["Antioquia", "Nariño", "Distrito Capital de Bogotá",
                                         "San Andrés, Providencia y Santa Catalina"],
                          "city": ["La Unión", "La Unión", "Bogotá", "San Andrés"]})
    out = match_regions(pairs, regions)
    assert list(out["mpio_code"]) == ["05400", "52399", "11001", "88001"]
    assert list(out["dpto_code"]) == ["05", "52", "11", "88"]


def test_city_unknown_keeps_department(topo):
    pairs = pd.DataFrame({"department": ["Antioquia"], "city": ["No Definido"]})
    out = match_regions(pairs, load_regions(topo))
    assert out.loc[0, "dpto_code"] == "05"
    assert pd.isna(out.loc[0, "mpio_code"])


def test_coverage_reports_unmatched(topo):
    pairs = pd.DataFrame({"department": ["Antioquia", "No Definido", "Antioquia"],
                          "city": ["Medellín", "No Definido", "Atlantis"]})
    matched = match_regions(pairs, load_regions(topo))
    rep = coverage(matched, weights=pd.Series([8, 1, 1]))
    assert rep["department_share"] == pytest.approx(0.9)
    assert rep["municipality_share"] == pytest.approx(0.8)
    assert ("Antioquia", "Atlantis", 1) in rep["unmatched_top"]


def test_single_municipality_department_needs_no_city(topo):
    pairs = pd.DataFrame({"department": ["Distrito Capital de Bogotá"], "city": ["No Definido"]})
    assert match_regions(pairs, load_regions(topo)).loc[0, "mpio_code"] == "11001"


def test_short_city_name_matches_official_long_name(topo):
    pairs = pd.DataFrame({"department": ["Valle del Cauca"], "city": ["Cali"]})
    assert match_regions(pairs, load_regions(topo)).loc[0, "mpio_code"] == "76001"


@pytest.mark.parametrize("secop,boundary", [("Don Matías", "Donmatías"),
                                             ("Mompós", "Santa Cruz De Mompox")])
def test_aliases_for_known_spellings(secop, boundary):
    assert normalize_name(secop) == normalize_name(boundary)
