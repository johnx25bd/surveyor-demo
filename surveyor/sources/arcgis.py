"""ArcGIS FeatureServer client — ONS boundaries and the IMD deprivation service.

These services are open (no key). They default to British National Grid or Web Mercator, so we
always force ``outSR=4326``. Paging is offset-based: loop while the response reports
``exceededTransferLimit`` (``maxRecordCount`` is 2000 on these layers).
"""

from __future__ import annotations

from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class ArcGISError(RuntimeError):
    pass


def query(
    service_url: str,
    *,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    return_geometry: bool = True,
    order_by: str | None = None,
    max_record_count: int = 2000,
) -> dict[str, Any]:
    """Query a FeatureServer layer, paging to completion.

    Returns a GeoJSON FeatureCollection when ``return_geometry`` is true, otherwise a dict with a
    ``features`` list of ``{attributes: {...}}`` records.
    """
    fmt = "geojson" if return_geometry else "json"
    collected: list[dict[str, Any]] = []
    offset = 0

    with httpx.Client(timeout=_TIMEOUT) as client:
        while True:
            params: dict[str, Any] = {
                "where": where,
                "outFields": out_fields,
                "outSR": out_sr,
                "f": fmt,
                "returnGeometry": str(return_geometry).lower(),
                "resultRecordCount": max_record_count,
                "resultOffset": offset,
            }
            if order_by:  # deterministic paging for large, multi-page result sets
                params["orderByFields"] = order_by

            data = _get_json(client, service_url, params)
            page = data.get("features", [])
            collected.extend(page)
            if not page or not data.get("exceededTransferLimit"):
                break
            offset += len(page)

    if return_geometry:
        return {"type": "FeatureCollection", "features": collected}
    return {"features": collected}


def _get_json(client: httpx.Client, url: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET + parse, with one retry on a timeout or 5xx. ArcGIS reports errors with HTTP 200."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = client.get(url, params=params)
            if resp.status_code >= 500:
                last_exc = ArcGISError(f"ArcGIS {resp.status_code} from {url}")
                continue
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                raise ArcGISError(f"ArcGIS error: {data['error']}")
            return data
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
    raise ArcGISError(f"ArcGIS request failed after retry: {last_exc}")
