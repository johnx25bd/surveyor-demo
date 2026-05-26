# Surveyor demo

This repository is a public, build-in-the-open walkthrough of making a thing called **Surveyor**, built live at the Geovation AI Agents workshop in May 2026. The point isn't only the finished product — it's the trail. Each phase leaves a durable artifact (a brief, a mockup, a slice of working code, a recording) so you can clone this repo, read the commit log, and walk the whole build yourself.

As of the bootstrap commit, what Surveyor actually *is* has not been decided. That is deliberate. The concept, the stack, the UI, the rough edges — all of it emerges across eight phases, each captured here as it happens. We don't plant the story; we record it.

## How to follow along

- [`WALKTHROUGH.md`](./WALKTHROUGH.md) — the index. One section per phase, linking the pull request, the recorded session, and the commits that carry the story.
- [Project board](https://github.com/users/johnx25bd/projects/8) — where each phase moves from Backlog to Published.
- [Milestone: Workshop 2026-05-27](https://github.com/johnx25bd/surveyor-demo/milestone/1) — every phase issue is tracked against it.

## The eight phases

0. Frame
1. Idea-gen
2. UI design
3. Architecture
4. Build phase 1
5. Build phase 2
6. Extension
7. Wrap

Phases 1–6 each produce a repo artifact and a recorded session, shipped as one pull request that is reviewed before it merges. Phases 0 and 7 are the live framing around the block.

## What's here now

Through phase 3 this was process scaffold and decision documents — no product code, by design. Phase 4 lands the first working slice: the Surveyor backend, an agent that turns a natural-language question into a sequence of tool calls over live OS and ONS data and shows its work as it goes. It runs from the command line; the browser UI is phase 5.

## Running Surveyor (build phase 1)

The backend is a Python application managed with [uv](https://docs.astral.sh/uv/), and needs Python 3.11 or newer.

```bash
uv sync                 # install dependencies into a local .venv
```

**API keys.** Two are needed, both kept server-side and never sent to the browser. Create a git-ignored `.env.dev` (or export them into the environment):

```
ANTHROPIC_API_KEY=...   # the agent loop
OS_DATA_HUB_KEY=...     # OS NGD feature fetches (a premium API)
```

ONS Nomis and the ONS/MHCLG ArcGIS services need no key. The agent runs on `claude-sonnet-4-6` by default; override it with `SURVEYOR_MODEL`.

**Ask a question:**

```bash
uv run python -m surveyor "How many health centres per 10,000 residents by local authority across Greater Manchester?"
uv run python -m surveyor "Population by local authority in England"
```

The agent prints its whole trace — every tool call, the small descriptor each returns, the render instructions for the map and chart, and a short written answer. Add `--dump-dir out/` to also write each resulting dataset to disk for inspection.

**Per-tool smokes**, each running one slice live against the real APIs:

```bash
uv run python -m scripts.try_boundaries
uv run python -m scripts.try_statistic
uv run python -m scripts.try_features      # needs OS_DATA_HUB_KEY
uv run python -m scripts.try_analysis      # the headline analysis chain, no model call
```
