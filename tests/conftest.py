"""Shared fixtures. Everything here runs offline — the live upstream calls stay behind the
``live`` marker (RUN_LIVE_TESTS=1), so the suite never burns a key in CI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import surveyor.app.main as main


@pytest.fixture
def client():
    # The context manager runs the app's lifespan (startup/shutdown), so the basemap client closes.
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_store():
    """Isolate the app-level DatasetStore between tests."""
    main.STORE._items.clear()
    yield
    main.STORE._items.clear()
