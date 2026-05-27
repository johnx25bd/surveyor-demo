"""Basemap proxy: the OS key must never reach the browser, and must be injected upstream."""

from __future__ import annotations

import httpx
import pytest

import surveyor.app.basemap as basemap


# ---- The vendored style is served keyless, with every OS URL rewritten to the proxy ----


def test_style_json_leaks_neither_host_nor_key(client):
    r = client.get("/api/basemap/style.json")
    assert r.status_code == 200
    assert "api.os.uk" not in r.text
    assert "key=" not in r.text
    assert "/api/basemap" in r.text


def test_style_json_themes(client):
    assert client.get("/api/basemap/style.json?theme=light").status_code == 200
    assert client.get("/api/basemap/style.json?theme=night").status_code == 200
    assert client.get("/api/basemap/style.json?theme=dark").status_code == 200


def test_style_json_unknown_theme_404(client):
    assert client.get("/api/basemap/style.json?theme=banana").status_code == 404


# ---- _strip_key handles realistic OS tile-URL query orderings ----


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"https://x/y.pbf?key=ABC123"', '"https://x/y.pbf"'),
        ('"https://x/y.pbf?key=ABC123&srs=3857"', '"https://x/y.pbf?srs=3857"'),
        ('"https://x/y.pbf?srs=3857&key=ABC123"', '"https://x/y.pbf?srs=3857"'),
        ('"https://x/y.pbf?key=ABC123"', '"https://x/y.pbf"'),
    ],
)
def test_strip_key(raw, expected):
    assert basemap._strip_key(raw) == expected


# ---- The proxy injects the key upstream and strips it from the response ----


def _use_mock(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(basemap, "_get_client", lambda: httpx.AsyncClient(transport=transport))


def test_proxy_injects_key_upstream_and_strips_from_tilejson(client, monkeypatch):
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        body = '{"tiles":["https://api.os.uk/maps/vector/v1/vts/{z}/{y}/{x}.pbf?key=SECRETKEY"]}'
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    _use_mock(monkeypatch, handler)
    r = client.get("/api/basemap/vts")

    assert r.status_code == 200
    assert "key=SECRETKEY" in seen["url"]  # injected on the upstream request
    assert "srs=3857" in seen["url"]  # default to Web Mercator (OS /vts is BNG by default)
    assert "SECRETKEY" not in r.text  # stripped from what the browser receives
    assert "api.os.uk" not in r.text
    assert "/api/basemap/vts/{z}/{y}/{x}.pbf" in r.text  # rewritten to the proxy


def test_proxy_keeps_caller_srs(client, monkeypatch):
    # A srs already on the request (from the rewritten TileJSON's tile URLs) is preserved, not doubled.
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"tile", headers={"content-type": "application/x-protobuf"})

    _use_mock(monkeypatch, handler)
    client.get("/api/basemap/vts/tile/6/40/30.pbf?srs=3857")
    assert seen["url"].count("srs=") == 1


def test_proxy_passes_tile_bytes_through(client, monkeypatch):
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\x1f\x8bPBFBYTES", headers={"content-type": "application/x-protobuf"}
        )

    _use_mock(monkeypatch, handler)
    r = client.get("/api/basemap/vts/3/4/2.pbf")

    assert r.status_code == 200
    assert r.content == b"\x1f\x8bPBFBYTES"
    assert r.headers["content-type"].startswith("application/x-protobuf")


def test_proxy_upstream_error_is_not_leaked(client, monkeypatch):
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to api.os.uk?key=SECRETKEY")

    _use_mock(monkeypatch, handler)
    r = client.get("/api/basemap/vts")

    assert r.status_code == 502
    assert "SECRETKEY" not in r.text  # the exception string (with the key) must not surface


def test_proxy_503_without_a_key(client, monkeypatch):
    monkeypatch.delenv("OS_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OS_DATA_HUB_KEY", raising=False)
    assert client.get("/api/basemap/vts").status_code == 503


def test_proxy_rejects_non_vts_paths(client, monkeypatch):
    # The allow-list runs before the key check, so a non-basemap OS path is 404, not proxied.
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")
    called = {"hit": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["hit"] = True
        return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

    _use_mock(monkeypatch, handler)
    assert client.get("/api/basemap/places/v1/find").status_code == 404
    assert client.get("/api/basemap/").status_code == 404
    assert called["hit"] is False  # never reached the upstream


def test_proxy_withholds_body_if_key_survives_stripping(client, monkeypatch):
    # If OS ever echoes the key somewhere _strip_key doesn't match, the positive check still catches it.
    monkeypatch.setenv("OS_DATA_HUB_KEY", "SECRETKEY")

    def handler(request: httpx.Request) -> httpx.Response:
        body = '{"note":"quote your key SECRETKEY when contacting support"}'
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    _use_mock(monkeypatch, handler)
    r = client.get("/api/basemap/vts")
    assert r.status_code == 502
    assert "SECRETKEY" not in r.text
