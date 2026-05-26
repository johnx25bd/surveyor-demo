"""OS NGD Features API client (OGC API Features, OFA v1). Premium — key in the ``key`` header.

Unlike the open ArcGIS/Nomis sources, this one differs in three ways verified against live calls:
``bbox`` is required; ``numberMatched`` comes back ``null`` so we cannot pre-size the result and
must follow the response's ``rel="next"`` link to page; and ``limit=100`` is a hard per-page
ceiling. The key never appears in the next href, so it is re-sent as a header on every page.

The type filter is applied server-side via CQL (passed in by the caller from the manifest), so an
unfiltered urban bbox never floods the result. A fetch that still exceeds ``max_features`` raises
``OverCapError`` — recoverable, so the agent narrows the bbox or picks a sparser type rather than
aggregating over truncated data.
"""

from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.os.uk/features/ngd/ofa/v1/collections"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_PAGE_LIMIT = 100  # OS NGD hard per-page ceiling
_CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


class OSNGDError(RuntimeError):
    pass


class OverCapError(OSNGDError):
    """A fetch matched more than ``max_features`` features within the bbox.

    Recoverable by design: the type filter is server-side, so this means the region/type is too
    dense, not that the call is misconfigured. The agent should narrow the bbox or pick a sparser
    feature type and retry — see the architecture doc, §6.
    """

    def __init__(self, max_features: int) -> None:
        super().__init__(
            f"feature fetch exceeded the cap of {max_features}; narrow the bbox or choose a "
            f"sparser feature type, then retry"
        )
        self.max_features = max_features


def fetch_items(
    collection: str,
    *,
    api_key: str,
    bbox: tuple[float, float, float, float],
    cql_filter: str | None = None,
    max_features: int = 2000,
) -> dict[str, Any]:
    """Fetch all matching features within ``bbox`` as a GeoJSON FeatureCollection (WGS84/CRS84).

    Pages by following ``rel="next"`` until a short page (fewer than ``_PAGE_LIMIT``) ends the set.
    Raises ``OverCapError`` once more than ``max_features`` have been collected.
    """
    headers = {"key": api_key, "Accept": "application/geo+json"}
    params: dict[str, Any] = {
        "bbox": ",".join(str(c) for c in bbox),
        "crs": _CRS84,
        "limit": _PAGE_LIMIT,
    }
    if cql_filter:
        params["filter"] = cql_filter
        params["filter-lang"] = "cql-text"

    collected: list[dict[str, Any]] = []
    url: str | None = f"{_BASE}/{collection}/items"
    request_params: dict[str, Any] | None = params  # first request only; the next href carries them

    with httpx.Client(timeout=_TIMEOUT) as client:
        while url:
            data = _get_json(client, url, request_params, headers)
            request_params = None
            page = data.get("features", [])
            collected.extend(page)
            if len(collected) > max_features:
                raise OverCapError(max_features)
            if len(page) < _PAGE_LIMIT:
                break
            url = next(
                (link["href"] for link in data.get("links", []) if link.get("rel") == "next"),
                None,
            )

    return {"type": "FeatureCollection", "features": collected}


def _get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any] | None,
    headers: dict[str, str],
) -> dict[str, Any]:
    """GET + parse, with one retry on a timeout or 5xx. A 4xx is non-retryable and wrapped."""
    last_exc: Exception | None = None
    for _ in range(2):
        try:
            resp = client.get(url, params=params, headers=headers)
            if resp.status_code >= 500:
                last_exc = OSNGDError(f"OS NGD {resp.status_code} from {url}")
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise OSNGDError(
                f"OS NGD {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
    raise OSNGDError(f"OS NGD request failed after retry: {last_exc}")
