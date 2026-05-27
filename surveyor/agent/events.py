"""Event sinks — the seam between the agent loop and its output surface (§10).

The loop emits structured events and does not know whether it is talking to a terminal or a
browser. ``CliSink`` prints a legible trace (build phase 1); ``SseSink`` (phase 2, stubbed) will
serialise the same events onto an HTTP stream — wiring the *identical* loop to the browser is then
a one-line sink swap. The ``EventSink`` protocol and ``ViewEvent`` live in ``tools.base`` (the tools
already depend on them); this module re-exports them and adds the concrete sinks, so there is one
definition and no import cycle.
"""

from __future__ import annotations

import json
import queue
import sys
from typing import Any

from ..tools.base import EventSink, ViewEvent  # re-exported; single source of truth

__all__ = [
    "EventSink",
    "ViewEvent",
    "CliSink",
    "SseSink",
    "STATUS",
    "MESSAGE",
    "TOOL_CALL",
    "TOOL_RESULT",
    "VIEW",
    "ERROR",
    "DONE",
]

# The §10 event names — shared by every sink so the loop and the sinks agree on one vocabulary.
STATUS = "status"
MESSAGE = "message"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
VIEW = "view"
ERROR = "error"
DONE = "done"


class _Style:
    """Minimal ANSI styling, disabled when the target stream is not a TTY (piped output stays clean)."""

    def __init__(self, stream: Any) -> None:
        self._on = stream.isatty()

    def __call__(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self._on else text


class CliSink:
    """Prints the agent's event stream as a readable, sequential trace."""

    def __init__(self) -> None:
        self._out = _Style(sys.stdout)
        self._err = _Style(sys.stderr)  # errors print to stderr; gate their colour on stderr's TTY
        self._mid_message = False  # a streamed reasoning line is currently open

    def emit(self, event: str, data: dict[str, Any]) -> None:
        s = self._out
        if event == MESSAGE:
            if not self._mid_message:
                sys.stdout.write("  ")
            sys.stdout.write(s("3", data.get("text", "")))  # italic reasoning, streamed inline
            sys.stdout.flush()
            self._mid_message = True
            return

        self._close_message()
        if event == STATUS:
            print(s("2", f"  · {data.get('state', '')}"))
        elif event == TOOL_CALL:
            args = ", ".join(f"{k}={v!r}" for k, v in (data.get("input") or {}).items())
            print(s("1;36", f"→ {data.get('name')}") + s("36", f"({args})"))
        elif event == TOOL_RESULT:
            print(s("32", f"← {self._summarise(data.get('descriptor', {}))}"))
        elif event == VIEW:
            print(
                s("1;35", f"▸ {data.get('kind')}")
                + s("35", f"  {data.get('handle')}  {data.get('encoding', {})}")
            )
        elif event == ERROR:
            print(self._err("1;31", f"✗ {data.get('message', '')}"), file=sys.stderr)
        elif event == DONE:
            print(s("2;32", "  ✓ done"))
        else:  # an unknown event — surface it rather than swallow (helps while developing)
            print(f"  ? {event}: {data}", file=sys.stderr)

    def _close_message(self) -> None:
        if self._mid_message:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._mid_message = False

    @staticmethod
    def _summarise(d: dict[str, Any]) -> str:
        if d.get("rendered"):
            return f"rendered {d.get('kind')} ← {d.get('handle')}"
        bits: list[str] = [str(d.get("handle", "?")), str(d.get("kind", ""))]
        if "count" in d:
            bits.append(f"{d['count']} {'features' if d.get('kind') == 'geo' else 'rows'}")
        if d.get("geometry_type"):
            bits.append(str(d["geometry_type"]))
        return "  ".join(b for b in bits if b)


class SseSink:
    """Serialise the agent's events onto a Server-Sent Events stream for the browser (§10).

    The loop is synchronous and blocking: it calls ``emit`` from a worker thread while the FastAPI
    route drains this sink's queue on the event loop and yields each frame. So ``emit`` only formats
    one SSE frame and enqueues it — no I/O, no blocking — and ``close`` enqueues a sentinel (``None``)
    that tells the draining side the run is over. The frame shape is the SSE wire format: a named
    event line plus a single JSON ``data`` line, terminated by a blank line.
    """

    SENTINEL = None  # enqueued by close(): signals "stream complete" to the consumer

    def __init__(self, frames: "queue.Queue[str | None]" | None = None) -> None:
        # An unbounded queue: emit never blocks the agent loop waiting on a slow client.
        self.frames: queue.Queue[str | None] = frames if frames is not None else queue.Queue()

    def emit(self, event: str, data: dict[str, Any]) -> None:
        self.frames.put(self._frame(event, data))

    def close(self) -> None:
        """Mark the end of the stream so the consumer can stop draining."""
        self.frames.put(self.SENTINEL)

    @staticmethod
    def _frame(event: str, data: dict[str, Any]) -> str:
        # default=str keeps a stray non-serialisable value (e.g. a tuple bbox) from killing the run.
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
