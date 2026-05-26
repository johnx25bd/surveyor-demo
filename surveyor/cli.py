"""``python -m surveyor "question"`` — run the agent once and print its trace (build phase 1).

This is the phase-1 entrypoint: no UI, no HTTP. It builds a CliSink, runs the loop, and (optionally)
dumps the resulting datasets to disk for inspection. Build phase 2 keeps this exact loop and swaps
the sink for an SSE stream behind a FastAPI route.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .agent import events, loop
from .config import ConfigError
from .data.store import DatasetStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="surveyor",
        description="Ask a question about UK geography; watch the agent show its work.",
    )
    parser.add_argument("question", help="The natural-language question to answer.")
    parser.add_argument(
        "--dump-dir",
        metavar="DIR",
        help="After the run, write each dataset in the store to DIR as JSON for inspection.",
    )
    args = parser.parse_args(argv)

    store = DatasetStore()
    sink = events.CliSink()
    print(f"ask: {args.question}\n")
    try:
        loop.run(args.question, sink, store=store)
    except ConfigError as exc:
        print(f"\nconfig error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — top-level guard: report, don't dump a raw traceback
        print(f"\nunexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.dump_dir:
        _dump(store, args.dump_dir)
    return 0


def _dump(store: DatasetStore, directory: str) -> None:
    """Write every live dataset to ``directory`` as JSON — a phase-1 peek into the store."""
    out = pathlib.Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for handle, (_, dataset) in store._items.items():
        path = out / f"{handle}.json"
        path.write_text(json.dumps(dataset.model_dump(), indent=2))
        print(f"  wrote {path}")
