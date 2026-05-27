"""OS Vector Tile basemap proxy — the key stays server-side (§11).

The browser never talks to ``api.os.uk`` directly; it talks to us. We serve a vendored OS stylesheet
(``Light`` for data-viz, ``Dark`` for night) with every OS URL rewritten to point back through this
proxy, and the proxy re-injects the OS Data Hub key on each upstream request. So the paid key never
appears in anything the browser can see — not the style JSON, not a tile URL, not the network tab.

The served style points its vector source at an explicit tiles template through us (the OS endpoint
is an ESRI document, not a TileJSON MapLibre can consume — see ``style``); MapLibre then fetches
tiles and glyphs back through the proxy, which injects the key and requests Web Mercator (srs=3857).
Sprites are served from public GitHub in the OS stylesheet, so they need no proxying.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..config import ConfigError, os_maps_key

log = logging.getLogger("surveyor.basemap")

router = APIRouter(prefix="/api/basemap", tags=["basemap"])

# One client for the life of the process: a single map render fans out to 50–200+ tile/glyph
# requests, so connection reuse and keep-alive to api.os.uk matter. Created lazily, closed on app
# shutdown via aclose_client().
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

_STYLES_DIR = Path(__file__).parent / "basemap_styles"
_OS_VTS_BASE = "https://api.os.uk/maps/vector/v1"
_PROXY_BASE = "/api/basemap"
# Theme name (what the frontend asks for) -> vendored stylesheet. Night reuses the OS Dark style.
_THEMES = {"light": "light.json", "dark": "dark.json", "night": "dark.json"}

# Strip a `key=...` query param (in either position) and tidy the dangling separator it leaves, so a
# proxied TileJSON never leaks the key back to the browser.
_KEY_PARAM = re.compile(r"([?&])key=[^&\"'\s}]*&?")
_DANGLING_SEP = re.compile(r"[?&](?=[\"'\s}])")


def _strip_key(text: str) -> str:
    return _DANGLING_SEP.sub("", _KEY_PARAM.sub(r"\1", text))


# The OS /vts endpoint returns an ESRI VectorTileServer document, not a standard MapLibre TileJSON,
# so a vector source that points at it via `url` leaves MapLibre unable to derive the tile scheme —
# it loads the document but never requests tiles. Define the source with an explicit Web Mercator
# tiles template instead. The OS VTS 3857 product carries data to ~z15; MapLibre over-zooms beyond.
_TILES_TEMPLATE = f"{_PROXY_BASE}/vts/tile/{{z}}/{{y}}/{{x}}.pbf?srs=3857"
_TILES_MAXZOOM = 15


@router.get("/style.json")
def style(theme: str = "light") -> Response:
    """A MapLibre style JSON, pointed at this proxy — no key in the served document.

    Two transforms on the vendored OS stylesheet: rewrite each vector source to an explicit tiles
    template (see above — the OS endpoint isn't a usable TileJSON for MapLibre), and host-swap the
    remaining OS URLs (``glyphs``, ``_sprite``) to the proxy. The GitHub-hosted ``sprite`` carries no
    key and is left untouched.
    """
    fname = _THEMES.get(theme.lower())
    if fname is None:
        raise HTTPException(status_code=404, detail=f"unknown basemap theme: {theme!r}")
    doc = json.loads((_STYLES_DIR / fname).read_text())
    for source in doc.get("sources", {}).values():
        if source.get("type") == "vector":
            source.pop("url", None)
            source["tiles"] = [_TILES_TEMPLATE]
            source["minzoom"] = 0
            source["maxzoom"] = _TILES_MAXZOOM
    text = json.dumps(doc).replace(_OS_VTS_BASE, _PROXY_BASE)
    return Response(content=text, media_type="application/json")


@router.get("/{path:path}")
async def proxy(path: str, request: Request) -> Response:
    """Proxy TileJSON / tiles / glyphs to the OS Vector Tile API with the key injected server-side."""
    try:
        key = os_maps_key()
    except ConfigError as exc:
        # 503: the server is missing config, not the client asking for something wrong.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    params = dict(request.query_params)
    params["key"] = key
    # MapLibre renders Web Mercator; the OS /vts endpoint defaults to the British National Grid
    # (EPSG:27700) tile matrix, which MapLibre can't draw. Default to srs=3857 so the TileJSON and
    # tiles come back in Web Mercator (the rewritten tile URLs already carry srs, so this is idempotent).
    params.setdefault("srs", "3857")
    try:
        upstream = await _get_client().get(f"{_OS_VTS_BASE}/{path}", params=params)
    except httpx.HTTPError as exc:
        # The exception's str() embeds the key-injected URL — log it server-side, never return it.
        log.warning("basemap upstream error for %s: %s", path, type(exc).__name__)
        raise HTTPException(status_code=502, detail="basemap upstream unavailable") from exc

    if upstream.status_code != 200:
        raise HTTPException(status_code=upstream.status_code, detail=f"OS VTS error for {path!r}")

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    if "json" in content_type:
        # TileJSON: rewrite OS URLs back through the proxy and strip the key it embedded in them.
        body = _strip_key(upstream.text.replace(_OS_VTS_BASE, _PROXY_BASE))
        return Response(content=body, media_type="application/json")
    # Tiles and glyphs: pass bytes through. Drop content-encoding (httpx already decompressed) and
    # cache hard — basemap tiles are immutable for the life of the key.
    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
