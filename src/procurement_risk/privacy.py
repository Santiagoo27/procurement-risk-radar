"""Privacy layer: allowlist projection and salted hashing of natural-person suppliers.

Rule: a supplier is a company only when its document type is NIT *and* the number looks like
a company NIT (9 digits starting with 8 or 9, optionally followed by a check digit). Natural
persons registered with a NIT (sole proprietors) carry their ID number as NIT, so anything
else, including empty or unknown types, is treated as a natural person (fail-safe).
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence

from procurement_risk import config

SALT_ENV = "PII_HASH_SALT"


class MissingSaltError(RuntimeError):
    """Raised when PII_HASH_SALT is not configured."""


def load_salt(env: Mapping[str, str] = os.environ) -> bytes:
    value = env.get(SALT_ENV, "").strip()
    if not value:
        raise MissingSaltError(
            f"{SALT_ENV} is not set; refusing to ingest without hashing natural persons."
        )
    return value.encode("utf-8")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip().upper()


def _looks_like_company_nit(number: str | None) -> bool:
    digits = re.sub(r"\D", "", number or "")
    if len(digits) == 10:
        digits = digits[:9]  # drop check digit
    return len(digits) == 9 and digits[0] in "89"


def is_natural_person(doc_type: str | None, doc_number: str | None = None) -> bool:
    if doc_type is None or _normalize(doc_type) != "NIT":
        return True
    return not _looks_like_company_nit(doc_number)


def hash_identifier(value: str | None, salt: bytes) -> str | None:
    if value is None or not value.strip():
        return None
    digest = hashlib.sha256(salt + value.strip().upper().encode("utf-8")).hexdigest()
    return "np_" + digest[:20]


def project(row: Mapping[str, str], columns: Sequence[str]) -> dict[str, str | None]:
    return {col: row.get(col) for col in columns}


def scrub_contract(row: Mapping[str, str], salt: bytes) -> dict[str, str | bool | None]:
    if not salt:
        raise MissingSaltError("an empty salt would make supplier hashes reversible")
    out: dict[str, str | bool | None] = dict(project(row, config.CONTRACT_COLUMNS))
    natural = is_natural_person(row.get("tipodocproveedor"), row.get("documento_proveedor"))
    if natural:
        out["documento_proveedor"] = hash_identifier(row.get("documento_proveedor"), salt)
        out["codigo_proveedor"] = hash_identifier(row.get("codigo_proveedor"), salt)
        out["proveedor_adjudicado"] = None
    out["supplier_is_natural_person"] = natural
    return out
