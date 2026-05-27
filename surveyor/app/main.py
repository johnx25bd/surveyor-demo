"""FastAPI app — the same agent loop, wired to a browser by swapping the event sink (§10).

Three surfaces:

- ``POST /api/query`` runs the loop and streams its trace as Server-Sent Events. The loop is
  synchronous and blocking, so it runs in a worker thread that feeds an ``SseSink`` queue while the
  route drains that queue on the event loop and yields frames.
- ``GET /api/datasets/{handle}`` serves the full GeoJSON or table behind a handle, so heavy geodata
  reaches the map without passing through the model or bloating the SSE stream.
- ``GET /api/basemap/*`` (mounted from ``basemap.py``) proxies the OS Vector Tile API with the key
  injected server-side.

State is one app-level ``DatasetStore`` shared by the query stream and the datasets endpoint —
single-instance by design (§11); a multi-user deployment would key stores by session.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from ..agent import events as ev
from ..agent import loop as agent_loop
from ..config import ConfigError
from ..data.store import DatasetStore
from .basemap import aclose_client
from .basemap import router as basemap_router

log = logging.getLogger("surveyor.app")

_ROOT = Path(__file__).resolve().parents[2]  # repo root: surveyor/app/main.py -> ../../
_WEB_DIST = _ROOT / "web" / "dist"

# Each /api/query spins a live agent run that spends the metered OS NGD and Anthropic keys, so cap
# concurrent runs and the request size. These are the cheap, in-process backstops for the no-auth
# posture (docs/02-architecture.md §11); a public deploy still wants per-IP rate limiting and auth.
MAX_QUESTION_CHARS = 2000
MAX_QUERY_BODY_BYTES = 64 * 1024
MAX_CONCURRENT_QUERIES = 4

_inflight = 0
_inflight_lock = threading.Lock()


def _acquire_slot() -> None:
    """Reserve a concurrency slot or raise 429. Pairs with _release_slot — every acquire that
    returns must be matched by exactly one release, on every exit path."""
    global _inflight
    with _inflight_lock:
        if _inflight >= MAX_CONCURRENT_QUERIES:
            raise HTTPException(status_code=429, detail="Too many queries in flight; try again shortly.")
        _inflight += 1


def _release_slot() -> None:
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - 1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await aclose_client()  # close the basemap proxy's shared httpx client on shutdown


app = FastAPI(title="Surveyor", version="0.1.0", lifespan=lifespan)
app.include_router(basemap_router)


@app.middleware("http")
async def guard_and_harden(request: Request, call_next):
    # Reject oversized query bodies before they are read (pydantic validation happens after the read).
    if request.method == "POST" and request.url.path == "/api/query":
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_QUERY_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


# One process, one store. Handles are unique per run; the TTL evicts stale datasets.
STORE = DatasetStore()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)

    @field_validator("question")
    @classmethod
    def _strip_and_require(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


def _run_agent(question: str, sink: ev.SseSink) -> None:
    """Run the blocking loop on a worker thread, turning any failure into trace events.

    Errors become an ``error`` + ``done`` pair rather than a torn stream or an HTTP 500 mid-body —
    the client always sees a clean end. ``close`` (in ``finally``) enqueues the sentinel that stops
    the draining side.
    """
    try:
        agent_loop.run(question, sink, store=STORE)
    except ConfigError as exc:
        # A config error is actionable and carries no secret — surface it to the user.
        sink.emit(ev.ERROR, {"message": str(exc)})
        sink.emit(ev.DONE, {"summary": "Configuration error — the run could not start."})
    except Exception:  # noqa: BLE001 — top-level guard: log detail server-side, tell the client little
        # The exception string can carry internal paths or a keyed upstream URL; keep it out of the
        # response and log it (with traceback) server-side instead.
        log.exception("agent run failed")
        sink.emit(ev.ERROR, {"message": "The run failed unexpectedly. Please try again."})
        sink.emit(ev.DONE, {"summary": "The run failed unexpectedly."})
    finally:
        sink.close()


@app.post("/api/query")
async def query(req: QueryRequest) -> StreamingResponse:
    # Cap concurrent live runs so a burst can't fan out unbounded metered-API spend and worker threads.
    _acquire_slot()
    try:
        sink = ev.SseSink()
        worker = threading.Thread(target=_run_agent, args=(req.question, sink), daemon=True)

        async def frames():
            worker.start()
            try:
                while True:
                    # Poll with a timeout rather than block forever: if the client disconnects, Starlette
                    # cancels this generator and we must be at an awaitable cancellation point, not parked
                    # in an un-interruptible Queue.get on a worker thread.
                    try:
                        frame = await asyncio.to_thread(sink.frames.get, True, 1.0)
                    except queue.Empty:
                        continue
                    if frame is None:  # the sentinel from sink.close()
                        break
                    yield frame
            finally:
                # On disconnect the agent loop can't be interrupted mid-step, but it's a daemon thread, so
                # cap the wait: don't pin this task for the rest of a multi-call run. On the normal path
                # the worker has already emitted its sentinel and exited, so this returns immediately.
                await asyncio.to_thread(worker.join, 5.0)
                _release_slot()

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # tell nginx-style proxies not to buffer the stream
            },
        )
    except BaseException:
        # The slot is released in frames()' finally once the stream runs. If we fail before handing the
        # generator to Starlette (so that finally can never run), release here so the slot can't leak.
        _release_slot()
        raise


@app.get("/api/datasets/{handle}")
async def dataset(handle: str) -> dict:
    """Full dataset behind a handle, for the browser to render (GeoJSON FeatureCollection / table)."""
    try:
        return STORE.get(handle).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Serve the built frontend last, so /api/* always wins. Mounted only once web/dist exists, so the
# backend runs (and is testable by curl) before the frontend is built.
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
