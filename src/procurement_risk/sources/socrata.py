"""Minimal Socrata (SODA 2.x) client with keyset pagination and retries."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator, Sequence

import httpx

from procurement_risk import config

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SocrataError(RuntimeError):
    """Raised when the API keeps failing after all retries."""


class SocrataClient:
    def __init__(
        self,
        domain: str = config.SOCRATA_DOMAIN,
        app_token: str | None = None,
        page_size: int = 50_000,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 120.0,
    ) -> None:
        if app_token is None:
            app_token = os.environ.get("SOCRATA_APP_TOKEN", "")
        headers = {"X-App-Token": app_token} if app_token else {}
        self._http = httpx.Client(
            base_url=f"https://{domain}", headers=headers, transport=transport, timeout=timeout
        )
        self.page_size = page_size
        self.max_retries = max_retries
        self._sleep = sleep

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, str]]:
        last_error: str = ""
        for attempt in range(self.max_retries):
            try:
                response = self._http.get(path, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = repr(exc)
            else:
                if response.status_code not in RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response.json()
                last_error = f"HTTP {response.status_code}"
            if attempt < self.max_retries - 1:
                self._sleep(2.0 * 2**attempt)
        raise SocrataError(f"{path} failed after {self.max_retries} attempts: {last_error}")

    def iter_pages(
        self, dataset_id: str, select: Sequence[str], where: str | None = None
    ) -> Iterator[list[dict[str, str]]]:
        """Yield pages of rows ordered by the internal `:id`, without the `:id` key."""
        last_id: str | None = None
        base_where = f"({where})" if where else None
        while True:
            clauses = [c for c in (base_where, f":id > '{last_id}'" if last_id else None) if c]
            params = {
                "$select": ",".join([":id", *select]),
                "$order": ":id",
                "$limit": str(self.page_size),
            }
            if clauses:
                params["$where"] = " AND ".join(clauses)
            rows = self._get(f"/resource/{dataset_id}.json", params)
            if not rows:
                return
            last_id = rows[-1][":id"]
            yield [{k: v for k, v in row.items() if k != ":id"} for row in rows]
