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
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent import events as ev
from ..agent import loop as agent_loop
from ..config import ConfigError
from ..data.store import DatasetStore
from .basemap import aclose_client
from .basemap import router as basemap_router

_ROOT = Path(__file__).resolve().parents[2]  # repo root: surveyor/app/main.py -> ../../
_WEB_DIST = _ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await aclose_client()  # close the basemap proxy's shared httpx client on shutdown


app = FastAPI(title="Surveyor", version="0.1.0", lifespan=lifespan)
app.include_router(basemap_router)

# One process, one store. Handles are unique per run; the TTL evicts stale datasets.
STORE = DatasetStore()


class QueryRequest(BaseModel):
    question: str


def _run_agent(question: str, sink: ev.SseSink) -> None:
    """Run the blocking loop on a worker thread, turning any failure into trace events.

    Errors become an ``error`` + ``done`` pair rather than a torn stream or an HTTP 500 mid-body —
    the client always sees a clean end. ``close`` (in ``finally``) enqueues the sentinel that stops
    the draining side.
    """
    try:
        agent_loop.run(question, sink, store=STORE)
    except ConfigError as exc:
        sink.emit(ev.ERROR, {"message": str(exc)})
        sink.emit(ev.DONE, {"summary": "Configuration error — the run could not start."})
    except Exception as exc:  # noqa: BLE001 — top-level guard: report, never leak a traceback
        sink.emit(ev.ERROR, {"message": f"{type(exc).__name__}: {exc}"})
        sink.emit(ev.DONE, {"summary": "The run failed unexpectedly."})
    finally:
        sink.close()


@app.post("/api/query")
async def query(req: QueryRequest) -> StreamingResponse:
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

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # tell nginx-style proxies not to buffer the stream
        },
    )


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
