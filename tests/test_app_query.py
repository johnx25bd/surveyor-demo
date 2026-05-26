"""POST /api/query: the sync-loop -> async-SSE bridge, including the error paths and shared store."""

from __future__ import annotations

import json

import surveyor.app.main as main
from surveyor.agent import events as ev
from surveyor.config import ConfigError
from surveyor.data.models import TableDataset


def _frames(text: str) -> list[str]:
    return [f for f in text.split("\n\n") if f.strip()]


def _event_names(text: str) -> list[str]:
    return [f.split("\n")[0].removeprefix("event: ") for f in _frames(text)]


def test_streams_events_in_order(client, monkeypatch):
    def fake_run(question, sink, store=None):
        sink.emit(ev.STATUS, {"state": "thinking"})
        sink.emit(ev.TOOL_CALL, {"id": "t1", "name": "fetch_boundaries", "input": {}})
        sink.emit(ev.TOOL_RESULT, {"id": "t1", "descriptor": {"handle": "ds_1", "kind": "geo"}})
        sink.emit(ev.VIEW, {"kind": "choropleth", "handle": "ds_1", "encoding": {}})
        sink.emit(ev.DONE, {"summary": "ok"})

    monkeypatch.setattr(main.agent_loop, "run", fake_run)
    r = client.post("/api/query", json={"question": "x"})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert _event_names(r.text) == ["status", "tool_call", "tool_result", "view", "done"]


def test_config_error_becomes_error_then_done(client, monkeypatch):
    def boom(question, sink, store=None):
        raise ConfigError("OS_DATA_HUB_KEY is not set")

    monkeypatch.setattr(main.agent_loop, "run", boom)
    r = client.post("/api/query", json={"question": "x"})

    assert r.status_code == 200  # the failure is in-band, not an HTTP error
    assert _event_names(r.text) == ["error", "done"]
    assert "OS_DATA_HUB_KEY" in r.text


def test_unexpected_error_is_caught_and_typed(client, monkeypatch):
    def boom(question, sink, store=None):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(main.agent_loop, "run", boom)
    r = client.post("/api/query", json={"question": "x"})

    assert "error" in _event_names(r.text)
    assert "RuntimeError: kaboom" in r.text


def test_query_and_datasets_share_one_store(client, monkeypatch):
    # A handle minted during the run must be fetchable afterwards from the same store.
    def fake_run(question, sink, store):
        handle = store.put(
            TableDataset(rows=[{"code": "E1", "pop": 7}], key_column="code", value_columns=["pop"])
        )
        sink.emit(ev.TOOL_RESULT, {"id": "t", "descriptor": {"handle": handle}})
        sink.emit(ev.DONE, {"summary": "ok"})

    monkeypatch.setattr(main.agent_loop, "run", fake_run)
    text = client.post("/api/query", json={"question": "x"}).text

    handle = next(
        json.loads(f.split("data: ", 1)[1])["descriptor"]["handle"]
        for f in _frames(text)
        if f.startswith("event: tool_result")
    )
    got = client.get(f"/api/datasets/{handle}")
    assert got.status_code == 200
    assert got.json()["rows"][0]["pop"] == 7


def test_missing_question_is_422(client):
    assert client.post("/api/query", json={}).status_code == 422
