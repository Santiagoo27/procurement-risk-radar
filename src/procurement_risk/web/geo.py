"""Match SECOP department/city names to the boundary file's DIVIPOLA codes."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

# Tokens that only appear in some spellings of the same place.
_DROP = {"de", "del", "y", "d", "c", "dc", "distrito", "capital", "archipielago", "especial",
         "turistico", "cultural", "historico", "portuario", "biodiverso"}
_UNKNOWN = {"no definido", "no definida", "sin definir", ""}
# Normalised SECOP spelling -> normalised boundary spelling, for cases the rules miss.
ALIASES: dict[str, str] = {
    "santafe antioquia": "santa fe antioquia",
    "don matias": "donmatias",
    "tolu viejo": "san jose toluviejo",
    "mompos": "santa cruz mompox",
}


def normalize_name(name: str | None) -> str | None:
    if name is None or (not isinstance(name, str) and pd.isna(name)):
        return None
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).casefold().strip()
    if folded in _UNKNOWN:
        return None
    tokens = [t for t in re.split(r"[^a-z0-9]+", folded) if t and t not in _DROP]
    key = " ".join(tokens)
    return ALIASES.get(key, key) or None


def load_regions(topo_path: Path) -> pd.DataFrame:
    topo = json.loads(Path(topo_path).read_text(encoding="utf-8"))
    rows = [g["properties"] for g in topo["objects"]["municipalities"]["geometries"]]
    regions = pd.DataFrame(rows, columns=["dpto_code", "dpto_name", "mpio_code", "mpio_name"])
    regions["dpto_key"] = regions["dpto_name"].map(normalize_name)
    regions["mpio_key"] = regions["mpio_name"].map(normalize_name)
    return regions


def _match_city(key: str | None, candidates: pd.DataFrame) -> str | None:
    if candidates.empty:
        return None
    if len(candidates) == 1:  # e.g. Bogotá, D.C. is a department with one municipality
        return candidates.iloc[0]["mpio_code"]
    if key is None:
        return None
    exact = candidates[candidates["mpio_key"] == key]
    if len(exact) == 1:
        return exact.iloc[0]["mpio_code"]

    # "Cartagena" vs "Cartagena De Indias", "Cali" vs "Santiago De Cali":
    # accept a unique whole-word prefix or suffix match.
    def partial(k: str | None) -> bool:
        if k is None:
            return False
        return (k.startswith(key + " ") or key.startswith(k + " ")
                or k.endswith(" " + key) or key.endswith(" " + k))

    loose = candidates[candidates["mpio_key"].map(partial)]
    return loose.iloc[0]["mpio_code"] if len(loose) == 1 else None


def match_regions(pairs: pd.DataFrame, regions: pd.DataFrame) -> pd.DataFrame:
    """Add dpto_code and mpio_code to a frame with `department` and `city` columns."""
    departments = regions.drop_duplicates("dpto_key").set_index("dpto_key")["dpto_code"]
    by_department = {code: frame for code, frame in regions.groupby("dpto_code")}
    out = pairs.copy()
    unique = out[["department", "city"]].drop_duplicates()
    codes = {}
    for dept, city in unique.itertuples(index=False):
        dpto = departments.get(normalize_name(dept))
        mpio = None
        if dpto is not None:
            mpio = _match_city(normalize_name(city), by_department.get(dpto, regions.iloc[:0]))
        codes[(dept, city)] = (dpto, mpio)
    out["dpto_code"] = [codes[(d, c)][0] for d, c in zip(out["department"], out["city"],
                                                          strict=True)]
    out["mpio_code"] = [codes[(d, c)][1] for d, c in zip(out["department"], out["city"],
                                                          strict=True)]
    return out


def coverage(matched: pd.DataFrame, weights: pd.Series, top: int = 20) -> dict:
    w = pd.Series(weights).reset_index(drop=True).astype(float)
    m = matched.reset_index(drop=True)
    total = w.sum()
    dept_ok, mpio_ok = m["dpto_code"].notna(), m["mpio_code"].notna()
    unmatched = (m.assign(w=w)[~mpio_ok].groupby(["department", "city"], dropna=False)["w"]
                 .sum().sort_values(ascending=False).head(top))
    return {
        "department_share": float(w[dept_ok].sum() / total) if total else 0.0,
        "municipality_share": float(w[mpio_ok].sum() / total) if total else 0.0,
        "unmatched_top": [(d, c, int(n)) for (d, c), n in unmatched.items()],
    }
