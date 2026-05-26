"""OS Vector Tile basemap proxy — the key stays server-side (§11).

The browser never talks to ``api.os.uk`` directly; it talks to us. We serve a vendored OS stylesheet
(``Light`` for data-viz, ``Dark`` for night) with every OS URL rewritten to point back through this
proxy, and the proxy re-injects the OS Data Hub key on each upstream request. So the paid key never
appears in anything the browser can see — not the style JSON, not a tile URL, not the network tab.

The OS source is a TileJSON endpoint (``sources.*.url``); MapLibre fetches it through us, we proxy it
and strip the key from the tile URLs it returns, and MapLibre then fetches tiles and glyphs back
through us too. Sprites are served from public GitHub in the OS stylesheet, so they need no proxying.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..config import ConfigError, os_maps_key

router = APIRouter(prefix="/api/basemap", tags=["basemap"])

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


@router.get("/style.json")
def style(theme: str = "light") -> Response:
    """A MapLibre style JSON with OS URLs rewritten to this proxy — no key in the served document.

    The rewrite is a whole-document host swap so every OS reference (source ``url``/``tiles``,
    ``glyphs``, and the ``sprite``/``_sprite`` fields) routes back through the proxy; GitHub-hosted
    sprites are left untouched because they carry no key.
    """
    fname = _THEMES.get(theme.lower())
    if fname is None:
        raise HTTPException(status_code=404, detail=f"unknown basemap theme: {theme!r}")
    doc = (_STYLES_DIR / fname).read_text().replace(_OS_VTS_BASE, _PROXY_BASE)
    return Response(content=doc, media_type="application/json")


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
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            upstream = await client.get(f"{_OS_VTS_BASE}/{path}", params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"basemap upstream error: {exc}") from exc

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
