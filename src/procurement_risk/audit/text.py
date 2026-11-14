"""Heuristic: does an amendment description describe an addition of value?"""

from __future__ import annotations

import re
import unicodedata

_ADDITION = re.compile(r"\badicion|\badicionar|\bmayor valor\b")
_VALUE = re.compile(r"\bvalor\b|\$|presupuest")


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def looks_like_value_addition(description: str | None) -> bool:
    if not description or not description.strip():
        return False
    text = _normalize(description)
    return bool(_ADDITION.search(text) and _VALUE.search(text))
