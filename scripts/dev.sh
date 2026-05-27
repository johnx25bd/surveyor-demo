#!/usr/bin/env bash
# Run the Surveyor dev stack: FastAPI backend (uvicorn :8000) + Vite frontend (:5173).
# Open http://localhost:5173 — Vite proxies /api/* to the backend, so it's one origin in the browser.
#
# Keys: put ANTHROPIC_API_KEY and OS_DATA_HUB_KEY in a git-ignored .env.dev at the repo root
# (config.py loads it on import). The map basemap needs OS_DATA_HUB_KEY; the national stat-only
# questions (ArcGIS + Nomis) run without it.
set -euo pipefail
cd "$(dirname "$0")/.."

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if [ ! -d web/node_modules ]; then
  echo "→ installing web dependencies…"
  (cd web && npm install)
fi

echo "→ backend   http://localhost:8000   (uvicorn --reload)"
uv run uvicorn surveyor.app.main:app --reload --port 8000 &

echo "→ frontend  http://localhost:5173   (vite)   ← open this one"
(cd web && npm run dev) &

wait
