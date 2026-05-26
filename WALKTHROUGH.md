# Walkthrough

The index to the Surveyor build. Each phase below fills in as its pull request merges: a link to the PR, the recorded session, the commits that carry the story, and a one-line summary of what happened.

Nothing here is filled in yet — that is the point. Check back as the phases land.

## Phase 0 — Frame

- PR: TBD
- Clip: TBD
- Key commits: TBD
- Summary: TBD

## Phase 1 — Idea-gen

- PR: #10
- Clip: [Part 1](https://youtu.be/AshYs9pfdAI), [Part 2](https://youtu.be/Qo3bWyz5MPE)
- Key commits: `c36f2e1` (concept brief), `08c6309` (session screenshot)
- Summary: Settled what Surveyor is — an agentic, show-your-work chat interface to UK national geospatial data (Ordnance Survey + ONS), committing to a three-pane shell while leaving visual design, interaction model, and the headline demo question deliberately open.

## Phase 2 — UI design

- PR: #11
- Clip: [Design session](https://youtu.be/eAucIBhZ9F4)
- Key commits: `9fcf90a` (UI mockup + design intent), `990c4df` (process screenshots)
- Summary: Turned the concept brief into an interactive mockup — one three-pane shell (chat / map / evidence rail) across three app states (empty → mid-query → result), worked through a candidate question about deprivation and green space. Kept the brief's open axes (brand mood, tool-call presentation, chart type) as live toggles rather than locking them, and left the headline demo question illustrative.

## Phase 3 — Architecture

- PR: #12
- Clip: TBD
- Key commits: `0df5225` (architecture decision doc), `cad5f5c` (revision grounded in live API validation)
- Summary: Made the binding technical decisions for v0.1 — a Python/FastAPI backend, a hand-rolled tool-use loop on the raw Anthropic SDK, operation-granular tools that exchange server-side dataset handles, and a composable analytical operation set (filter / aggregate / normalize / rank / relate / attach) rather than a fixed pipeline. Validated every API shape against live calls to the OS NGD, ONS Nomis, and ONS/MHCLG ArcGIS services, recorded the feasible-question envelope (OS NGD's 100-features-per-page ceiling makes feature-aggregation regional, not national), and scoped build phase 1 to a CLI-tested backend.

## Phase 4 — Build phase 1

- PR: TBD
- Clip: TBD
- Key commits: TBD
- Summary: TBD

## Phase 5 — Build phase 2

- PR: TBD
- Clip: TBD
- Key commits: TBD
- Summary: TBD

## Phase 6 — Extension

- PR: TBD
- Clip: TBD
- Key commits: TBD
- Summary: TBD

## Phase 7 — Wrap

- PR: TBD
- Clip: TBD
- Key commits: TBD
- Summary: TBD
