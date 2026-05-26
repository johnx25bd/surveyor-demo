"""ONS Nomis API client — statistics by geography, keyed by GSS code. No API key needed.

Requests CSV (`.data.csv`) for a flat, cheap parse. The dataset id, geography TYPE, and pinned
dimensions are supplied by the manifest, because Nomis TYPE codes are dataset- and vintage-specific.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import httpx

_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class NomisError(RuntimeError):
    pass


def fetch_csv(
    dataset_id: str, geography: str, select: list[str], dims: dict[str, int]
) -> list[dict[str, str]]:
    """GET ``{dataset}.data.csv`` and parse it into a list of row dicts."""
    url = f"{_BASE}/{dataset_id}.data.csv"
    params: dict[str, Any] = {"geography": geography, "select": ",".join(select), **dims}
    last_exc: Exception | None = None
    for _ in range(2):
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return list(csv.DictReader(io.StringIO(resp.text)))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
    raise NomisError(f"Nomis request failed after retry: {last_exc}")
