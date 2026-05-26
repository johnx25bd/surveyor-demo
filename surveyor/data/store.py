"""In-memory, session-scoped store for datasets, keyed by opaque handles.

Single-instance and TTL-bounded — adequate for v0.1 (local use or a single deployed process).
Horizontal scaling would need a shared store; see the architecture doc, §11.
"""

from __future__ import annotations

import time
import uuid

from .models import Dataset


class DatasetStore:
    def __init__(self, ttl_seconds: float = 1800) -> None:
        self._items: dict[str, tuple[float, Dataset]] = {}
        self._ttl = ttl_seconds

    def put(self, dataset: Dataset) -> str:
        handle = f"ds_{uuid.uuid4().hex[:8]}"
        self._items[handle] = (time.monotonic(), dataset)
        return handle

    def get(self, handle: str) -> Dataset:
        self._evict()
        try:
            return self._items[handle][1]
        except KeyError as exc:
            raise KeyError(f"unknown or expired dataset handle: {handle!r}") from exc

    def items(self) -> list[tuple[str, Dataset]]:
        """(handle, dataset) pairs for every live dataset — a read-only view for CLI inspection."""
        self._evict()
        return [(handle, ds) for handle, (_, ds) in self._items.items()]

    def _evict(self) -> None:
        now = time.monotonic()
        for handle in [h for h, (ts, _) in self._items.items() if now - ts > self._ttl]:
            del self._items[handle]
