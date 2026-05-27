# Walkthrough

The index to the Surveyor build. Each phase links its pull request, the recorded session where one exists, the commits that carry the story, and a one-line summary of what happened.

Phases 1 through 6 are written up below — clone the repo and you can follow each one through its commits. Phases 0 and 7 are the live framing around the block, with no durable artifact of their own.

## Phase 0 — Frame

The spoken open to the block — framing the day and the format, with no durable artifact in the repo.

## Phase 1 — Idea-gen

- PR: #10
- Clip: [Part 1](https://youtu.be/AshYs9pfdAI), [Part 2](https://youtu.be/Qo3bWyz5MPE)
- Key commits: `d3b6569` (concept brief), `54b07b4` (session screenshot)
- Summary: Settled what Surveyor is — an agentic, show-your-work chat interface to UK national geospatial data (Ordnance Survey + ONS), committing to a three-pane shell while leaving visual design, interaction model, and the headline demo question deliberately open.

## Phase 2 — UI design

- PR: #11
- Clip: [Design session](https://youtu.be/eAucIBhZ9F4)
- Key commits: `b2d0340` (UI mockup + design intent), `4db6e7d` (process screenshots)
- Summary: Turned the concept brief into an interactive mockup — one three-pane shell (chat / map / evidence rail) across three app states (empty → mid-query → result), worked through a candidate question about deprivation and green space. Kept the brief's open axes (brand mood, tool-call presentation, chart type) as live toggles rather than locking them, and left the headline demo question illustrative.

## Phase 3 — Architecture

- PR: #12
- Clip: TBD
- Key commits: `2b4a3d0` (architecture decision doc), `d998f2b` (revision grounded in live API validation)
- Summary: Made the binding technical decisions for v0.1 — a Python/FastAPI backend, a hand-rolled tool-use loop on the raw Anthropic SDK, operation-granular tools that exchange server-side dataset handles, and a composable analytical operation set (filter / aggregate / normalize / rank / relate / attach) rather than a fixed pipeline. Validated every API shape against live calls to the OS NGD, ONS Nomis, and ONS/MHCLG ArcGIS services, recorded the feasible-question envelope (OS NGD's 100-features-per-page ceiling makes feature-aggregation regional, not national), and scoped build phase 1 to a CLI-tested backend.

## Phase 4 — Build phase 1

- PR: #14
- Clip: TBD
- Key commits: `4aa79b4` (scaffold + data model), `ea12921` (the §7 analytical operation set), `760987c` (the hand-rolled agent loop)
- Summary: Built the phase-1 backend per the architecture doc — backend-first, tested from a CLI against live APIs, no UI. Three source clients (ONS/MHCLG ArcGIS, ONS Nomis, OS NGD), three fetch tools, the six composable analytical operations (filter / aggregate / normalize / rank / relate / attach), two render tools, a tool registry, and a hand-rolled Anthropic tool-use loop that streams its trace through a swappable event sink. The headline question — health-centre provision per 10,000 residents by local authority across Greater Manchester — runs end to end from `python -m surveyor`, with the agent composing the full chain autonomously; the national stat-only fallback (population by local authority) runs too. Every upstream API shape was validated against live calls before the code was written, and the build was reviewed in two parallel passes with the findings triaged before merge.

## Phase 5 — Build phase 2

- PR: #20
- Clip: [UI demo](https://youtu.be/By9EBr5duwA)
- Key commits: `e13871c` (SseSink), `c048e66` (HTTP/SSE query + datasets routes), `3f8467f` (OS Vector Tile basemap proxy), `c3c4a3f` (three-pane React UI)
- Summary: Wired the unchanged phase-1 agent loop to the browser by swapping the event sink. A FastAPI layer streams the agent's trace as Server-Sent Events (`POST /api/query`) and serves the data behind each handle (`GET /api/datasets/{handle}`); a backend proxy fronts the OS Vector Tile API so the metered key stays server-side. The frontend is a Vite + React + TypeScript app built on the Ordnance Survey design system — a three-pane shell (chat / map / evidence rail) that renders the live show-your-work tool trace, an OS-vector-tile choropleth (GeoDataViz ramps, quantile class breaks) with a ranked bar chart, and hover/selection synced across all three panes. The same headline question and national fallback that ran from the CLI in phase 4 now run in the browser, unchanged loop underneath.

## Phase 6 — Extension

- PR: #23
- Clip: TBD
- Key commits: `6c9cf25` (West Midlands region + library feature type), `c9d1567` (points overlay view kind), `6c3db58` (point overlay on the map), `bd6b8a2` (proximity question in the UI)
- Summary: Extended the curated manifest and the render layer to demonstrate a proximity question — "How many health centres in the West Midlands are within 800m of a library?" Added the West Midlands region and the library feature type to the capability manifest, a `points` overlay view kind to the render layer with its matching map overlay in the frontend, and surfaced the new question among the UI's suggestions. The question exercises the `relate` operation end to end — the agent fetches both feature sets, relates them by distance, and the map adds a point overlay — with no change to the agent loop or the six-operation analytical set. The extension is data plus one render kind: the composability bet from phase 3 paying off.

## Phase 7 — Wrap

The spoken close to the block — wrap-up and reflection, with no durable artifact in the repo.
