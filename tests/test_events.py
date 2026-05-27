"""SseSink: SSE frame format, the close sentinel, and resilience to odd payload values."""

from __future__ import annotations

import json

from surveyor.agent.events import DONE, TOOL_CALL, VIEW, SseSink


def _data(frame: str) -> dict:
    return json.loads(frame.split("\n")[1][len("data: ") :])


def test_frame_is_named_event_with_json_data():
    sink = SseSink()
    sink.emit(TOOL_CALL, {"name": "fetch_boundaries", "input": {"region": "england"}})
    frame = sink.frames.get_nowait()
    assert frame.startswith("event: tool_call\n")
    assert frame.endswith("\n\n")
    assert _data(frame) == {"name": "fetch_boundaries", "input": {"region": "england"}}


def test_close_enqueues_sentinel():
    sink = SseSink()
    sink.emit(DONE, {"summary": "ok"})
    sink.close()
    assert sink.frames.get_nowait().startswith("event: done")
    assert sink.frames.get_nowait() is None


def test_non_serializable_value_falls_back_to_str():
    # The loop emits plain dicts, but default=str means an exotic value can't kill a run.
    sink = SseSink()
    sink.emit(VIEW, {"weird": {1, 2}})  # a set is not JSON-serializable
    assert _data(sink.frames.get_nowait()) == {"weird": "{1, 2}"}


def test_a_shared_queue_can_be_injected():
    import queue

    q: queue.Queue = queue.Queue()
    SseSink(q).emit(DONE, {"summary": "x"})
    assert q.get_nowait().startswith("event: done")
