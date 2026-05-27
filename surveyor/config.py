"""Settings from the environment, with a lightweight ``.env`` loader (no extra dependency).

Keys live only in the environment — never in code, never sent to the browser: ``OS_DATA_HUB_KEY``
for OS NGD, ``ANTHROPIC_API_KEY`` for the agent loop. A local, git-ignored ``.env.dev`` is loaded
on import so the CLI and smoke scripts pick keys up without a manual ``export``; real environment
variables always win (``setdefault``), so nothing here overrides a deployed config.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # repo root — surveyor/ sits one level down


def _load_env_file(name: str) -> None:
    path = _ROOT / name
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]  # strip matched surrounding quotes (e.g. KEY="abc")
        os.environ.setdefault(key.strip(), value)


# .env.dev (local) first, then .env as a fallback; setdefault keeps real env vars authoritative.
for _name in (".env.dev", ".env"):
    _load_env_file(_name)


class ConfigError(RuntimeError):
    pass


def os_data_hub_key() -> str:
    key = os.environ.get("OS_DATA_HUB_KEY", "").strip()
    if not key:
        raise ConfigError("OS_DATA_HUB_KEY is not set (needed for fetch_features against OS NGD)")
    return key


def os_maps_key() -> str:
    """Key for the OS Vector Tile basemap proxy.

    Prefers a dedicated ``OS_MAPS_API_KEY`` if set (use it when the basemap lives on a different OS
    Data Hub project than the NGD features key); otherwise reuses ``OS_DATA_HUB_KEY``. Either way the
    key stays server-side — the basemap proxy injects it, the browser never sees it.
    """
    key = (os.environ.get("OS_MAPS_API_KEY") or os.environ.get("OS_DATA_HUB_KEY") or "").strip()
    if not key:
        raise ConfigError(
            "no OS basemap key set (set OS_MAPS_API_KEY, or OS_DATA_HUB_KEY to reuse the NGD key)"
        )
    return key


def anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise ConfigError("ANTHROPIC_API_KEY is not set (needed for the agent loop)")
    return key


def model() -> str:
    """The Claude model id the agent loop runs on; override with SURVEYOR_MODEL."""
    return os.environ.get("SURVEYOR_MODEL", "").strip() or "claude-sonnet-4-6"
