# Surveyor — Architecture

This document makes the binding technical decisions for Surveyor v0.1: the language and
runtime, the agent loop, the tool interface every data source and capability plugs into, the
data model, how a question becomes a map and a chart, the file layout, and the scope of the
first build slice. It is written so a coding agent could scaffold the project from here without
further architectural input.

Inputs: [`00-idea.md`](00-idea.md) (the concept) and [`01-ui-mockup.md`](01-ui-mockup.md) (the
three-pane shell). Those documents are *intent*, not specification — the stack, tool surface,
data models, and interfaces below are designed here from first principles and grounded in the
real behaviour of the upstream APIs, which we verified against live responses while writing this.

The API endpoints, parameters, and limits cited throughout were checked against live calls to
OS NGD, ONS Nomis, and the ONS/MHCLG ArcGIS services in May 2026. Where a fact is load-bearing
and we could not confirm it, it is flagged as an open question rather than assumed.

---

## 1. Architecture at a glance

Surveyor is a single deployable web application. A Python backend runs an LLM agent that
translates a natural-language question into a sequence of tool calls against live UK geospatial
and statistics APIs, aggregates the results, and emits render instructions. A thin frontend
renders the streamed agent trace, a map, and a chart. Every tool call is visible because the
agent loop emits it — transparency is a structural property of the loop, not a UI affordation.

```
                          ┌─────────────────────────────────────────────┐
  Browser (thin client)   │  FastAPI app  (single deployable unit)       │
  ┌───────────────────┐   │                                             │
  │ chat trace        │   │  POST /api/query  ──► Agent loop            │
  │ map (MapLibre)    │◄──┼── SSE event stream    (Anthropic SDK,       │
  │ chart             │   │                        hand-rolled)         │
  └───────────────────┘   │                          │                  │
        │  GET /api/datasets/{handle}                 │ calls tools      │
        └────────────────►│                           ▼                  │
                          │   Tool registry ──► fetch / compute / render │
                          │        │                  │                  │
                          │        ▼                  ▼                  │
                          │   Source clients     DatasetStore (handles)  │
                          └────────┼──────────────────────────────────── ┘
                                   ▼
              OS NGD Features API · ONS Nomis API · ONS/MHCLG ArcGIS services
                              (live, server-side, keys never reach the browser)
```

The load-bearing ideas, each justified below:

- **Operation-granular tools** — one tool per logical step, so the trace reads as a sequence of
  comprehensible actions and the extension story is "add a tool, register it."
- **Dataset handles** — tools exchange small server-side references, never raw geodata through
  the model's context. The agent reasons over metadata; the megabytes stay on the server.
- **An event sink the loop writes to** — the same agent loop drives a CLI trace (build phase 1)
  and a browser SSE stream (build phase 2) by swapping the sink, not the loop.

---

## 2. Decision — language and runtime: Python + FastAPI

**Decision: a Python backend on FastAPI, with the agent running server-side, served as a single
deployable unit that also serves a thin static frontend.**

| | **Python + FastAPI** (chosen) | TypeScript full-stack | Python backend + separate JS framework |
|---|---|---|---|
| Geospatial compute | shapely / geopandas / pyproj — first-class | Turf.js / proj4 — workable, shallower | same as chosen |
| Live-demo debuggability | Presenter is fluent; one language to reason about on stage | Presenter less fluent | two languages |
| Deploy | One unit (FastAPI serves API + static frontend) | One unit, trivial | Two services or a bundled container |
| Agent SDK maturity | Anthropic Python SDK — well-understood | Mature | same as chosen |
| Streaming to UI | SSE from FastAPI — straightforward | Framework-native | SSE, across a language boundary |

**Why.** Two factors decide it. First, this runs live on the presenter's laptop, so
presenter fluency and the ability to debug on stage outweigh ecosystem novelty — Python wins
decisively there. Second, the analytical core is spatial work (point-in-polygon aggregation,
reprojection, and the buffer/proximity operations the roadmap points toward), and Python's
geospatial stack is years ahead of JavaScript's. The one cost — JavaScript would integrate the
frontend more tightly — is small, because the frontend is deliberately thin and talks to the
backend over a simple SSE stream and one data endpoint.

**Deployment is in scope.** v0.1 has no authentication, but it is designed to deploy, not only
to run locally. FastAPI serves the API, the SSE stream, and the built static frontend from one
process, so the same artifact runs under `uvicorn` locally and in a container anywhere
(Fly.io, Render, Railway). All API keys live server-side as environment variables and never
reach the browser. See [§10](#10-deployment-posture) for the one real risk this opens.

---

## 3. Decision — the agent loop: raw Anthropic SDK, hand-rolled

**Decision: a hand-rolled tool-use loop on the raw Anthropic Python SDK. No agent framework.**

| | **Raw Anthropic SDK** (chosen) | A framework (LangChain, etc.) | Claude Agent SDK |
|---|---|---|---|
| Transparency | Total — nothing is hidden; we emit every step | Abstracted behind the framework | Loop managed for us |
| Dependencies | One SDK | Heavy | Heavier than the job |
| Teachability (this is a workshop) | The loop is the lesson | Framework is the lesson | Less to see |
| Fit for a 2-source, single-turn query | Exact | Overkill | Built for long-horizon autonomy |

**Why.** "Show your work" is the product. A hand-rolled loop makes the agent's mechanics fully
visible and fully ours to instrument — when the agent calls a tool, *we* decide what gets
emitted to the trace, because we wrote the dispatch. The presenter knows this SDK well, which
again matters for live debugging. And for a workshop, the loop being legible *is* the teaching
content; a framework would hide exactly what the audience came to see. Frameworks earn their
weight on multi-agent orchestration and long-horizon memory — neither of which v0.1 needs.

The loop is the standard Anthropic tool-use cycle: send the conversation plus the tool schemas;
if the model returns `tool_use` blocks, dispatch each to its handler, append the `tool_result`
blocks, and loop; stop when the model returns a final text answer (or a step ceiling is hit).
Each iteration emits structured events (see [§8](#8-data-flow-and-streaming)).

---

## 4. Decision — the tool interface

This is the heart of the architecture: the shape every data source and every future capability
follows. The analytical goal — *spatial aggregation with normalisation* — decomposes into one
legible chain:

> resolve boundaries → fetch features → fetch a statistic → aggregate features into boundaries →
> normalise → render map + chart

**Decision: operation-granular tools.** One tool per logical step, not one mega-tool per source
and not one tool per dataset.

| Granularity | Trace legibility | Extension cost | Agent cognitive load |
|---|---|---|---|
| One mega-tool per source | Poor — one opaque call hides the work | Low | High (huge schemas) |
| **One tool per operation** (chosen) | **Excellent — each call is one step** | **Low — add a tool, register it** | **Low — small, sharp schemas** |
| One tool per dataset/collection | OK | Explodes the surface | High (prompt bloat) |

A trace that reads *"got 309 LAD boundaries → fetched health-centre sites → counted per LAD →
fetched population → normalised per 10,000 residents → rendered choropleth"* is the transparency
principle made literal. It also gives a clean extension rule, which is what the issue asks for:

- **A new data source** is a new `fetch_*` tool plus a thin source client.
- **A new capability** (buffer, proximity, isochrone) is a new compute tool.
- The agent **recomposes existing tools**; adding one is a registration, not a refactor.

### 4.1 Dataset handles — the idea underneath

Tools do **not** pass raw GeoJSON through the model's context. A national boundary set is several
megabytes; a feature pull is thousands of geometries. Pushing that through the model would be
slow, expensive, and would drown the trace. Instead:

- A server-side **`DatasetStore`** holds the actual data, keyed by an opaque **handle** id.
- A tool returns a small **descriptor** to the model — counts, bounds, CRS, columns, a sample —
  *not* the data.
- Compute tools take handle ids in, write a new dataset, and return a new handle.
- `render_*` tools take a handle and emit a *view event*; the **browser** then fetches the full
  data directly via `GET /api/datasets/{handle}` to draw it.

The agent reasons over **metadata and handles**; the heavy geodata never enters its context and
never round-trips through the model. This keeps the loop cheap, the trace clean, and the data
inspectable — and it cleanly separates *what the agent decided* from *the megabytes it decided
over*.

---

## 5. The data model

Two dataset shapes, one universal join key, one CRS policy.

**`GeoDataset`** — a GeoJSON `FeatureCollection`, the CRS it is in, the geometry type, and the
property that holds the join key (a GSS code, where applicable).

**`TableDataset`** — rows keyed by GSS code, with one or more named value columns. This is what
statistics and aggregation results are.

**`DatasetDescriptor`** — the small object a tool returns *to the model*:

```jsonc
{
  "handle": "ds_7f3a",
  "kind": "geo",                 // "geo" | "table"
  "count": 309,
  "crs": "EPSG:4326",            // geo only
  "geometry_type": "Polygon",    // geo only
  "bbox": [-3.1, 53.3, -1.9, 53.7],
  "key_column": "LAD21CD",
  "columns": ["LAD21CD", "LAD21NM"],
  "sample": [ /* 1–2 rows, truncated geometry */ ]
}
```

**The universal join key is the GSS code** (`E06000001`, `E08000003`, …). Boundaries carry it
(`LAD21CD`, `LSOA21CD`), Nomis returns it (`GEOGRAPHY_CODE`), and IMD carries it (`lsoa11cd`,
plus a `LADcd` for rolling up). Every join in the aggregate→normalise chain pivots on this one
key, which is why it sits explicitly in the descriptor.

**The `DatasetStore`** is session-scoped and in-memory for v0.1: `put(dataset) -> handle`,
`get(handle) -> dataset`, with a TTL so a handle outlives the request long enough for the
browser to fetch it. In-memory means single-instance — acceptable for v0.1, flagged in
[§10](#10-deployment-posture).

### 5.1 CRS policy — explicit in the data, invisible as a decision

CRS is an **attribute of every dataset**, not a tool the agent reasons about. The research
showed the sources disagree on defaults, so normalisation happens at fetch time:

- **OS NGD** returns WGS84 (CRS84) **by default** — no action needed.
- **ArcGIS** services default to British National Grid (boundaries, EPSG:27700) or Web Mercator
  (IMD, EPSG:102100). Every ArcGIS `fetch_*` tool forces `outSR=4326`.

So every dataset enters the store in **WGS84 (EPSG:4326)**, ready for the web map. When a compute
tool needs *metric* geometry — area, density per km², and the buffer/proximity operations the
roadmap points to — it reprojects to **British National Grid (EPSG:27700)** internally via
`pyproj`, and that reprojection **surfaces in the trace** (e.g. *"reprojected features 4326→27700
before area calculation"*). Pure point-in-polygon containment is topologically valid in WGS84 at
these scales and needs no reprojection. The agent never calls a `reproject` tool — making it
reason about projections would add load without analytical insight — but the projection is always
visible in handle metadata and in the aggregate step's trace.

---

## 6. The tool catalog (v0.1)

Concrete signatures. Inputs are the JSON-schema parameters the model sees; each returns a
`DatasetDescriptor` unless noted. Real upstream parameters are given so this is buildable.

### Fetch tools (I/O → a new dataset)

**`fetch_boundaries(geography_level, area_filter)` → GeoDataset**
ArcGIS FeatureServer query, `f=geojson`, `outSR=4326`, paged by `resultOffset` (`maxRecordCount`
is 2000; watch `exceededTransferLimit`). `geography_level ∈ {local_authority, lsoa, msoa}`;
`area_filter` is an attribute predicate or named region (e.g. England → `where=LAD21CD LIKE 'E%'`,
which returns 309 LADs). Join key `LAD21CD` / `LSOA21CD`.
Example service: `services1.arcgis.com/ESMARspQHYMw9BZ9/.../Local_Authority_Districts_December_2021_UK_BGC_2022/FeatureServer/0/query`.
Uses **BGC** (generalised, clipped) boundaries for fast rendering; drops to **BSC** if a wide
LSOA extent is ever requested.

**`fetch_statistic(metric, geography_level, area_filter)` → TableDataset (keyed by GSS code)**
ONS Nomis, no API key. v0.1 ships `metric = population` →
`dataset/NM_2021_1.data.csv?geography={parent}TYPE{n}&measures=20100&c2021_restype_3=0&select=GEOGRAPHY_CODE,GEOGRAPHY_NAME,OBS_VALUE`.
The `(dataset id, geography TYPE, pinned dimensions)` for each metric come from the capability
manifest ([§7](#7-capability-discovery-and-the-curated-manifest)), because Nomis TYPE codes are
dataset- and vintage-specific. CSV is parsed for simplicity.

**`fetch_deprivation(geography_level, fields)` → TableDataset (keyed by GSS code)**
The IMD 2019 ArcGIS service, `returnGeometry=false`, `outFields=lsoa11cd,IMDScore,IMDDec0,LADcd`.
Separate from `fetch_statistic` because it is a different source and shape. **IMD is keyed on
2011 LSOAs**; v0.1 sidesteps the 2011/2021 boundary drift by rolling IMD up to LAD via the
service's own `LADcd` field rather than joining at LSOA.

**`fetch_features(feature_type, bbox, max_features)` → GeoDataset**
OS NGD Features API, key in the `key` **header**, WGS84 by default, `bbox` **required**, paged at
`limit=100` (a hard ceiling). `feature_type` resolves through the manifest to a `(collection, CQL
filter)` pair — e.g. `health_centre → (lus-fts-site, description='Health Centre')`. `max_features`
caps the paging (default 2,000; hard ceiling 5,000); exceeding it returns an **over-cap signal to
the agent** so it narrows the query *visibly* rather than the system silently stalling. The
100/page ceiling is why feature aggregation is a **regional**, bbox-bounded operation, not a
national one (see [§11](#11-the-feasible-question-envelope)).

### Compute tools (data → derived data)

**`aggregate(features, boundaries, op)` → TableDataset (keyed by GSS code)**
Spatial join of `features` into `boundaries` (point-in-polygon, or polygon centroid containment),
producing a value per boundary. `op ∈ {count, sum:<field>}`. Implemented with shapely /
geopandas; reprojects to EPSG:27700 only if the op is metric.

**`normalize(numerator, denominator, op, per)` → TableDataset**
Joins two tables on GSS code and combines them. `op ∈ {ratio, rate}`; `per` scales a rate
(e.g. `per = 10000` → "per 10,000 residents"). Output is the ranked, normalised table.

**`join_to_boundaries(table, boundaries, value_column)` → GeoDataset**
Attaches a table's value column onto boundary polygons by GSS code, producing the choropleth-ready
GeoDataset.

### Render tools (a dataset → a view instruction)

**`render_choropleth(geo_dataset, value_column, title)` → view event**
**`render_chart(table, value_column, label_column, kind, title)` → view event** (`kind` defaults
to a ranked bar)

Render tools do not return data to the model — they emit a `view` event naming a handle and an
encoding. The browser fetches the handle's data and draws it. In build phase 1 (no UI), the CLI
sink prints the view instruction and writes the dataset to disk.

### Discovery tools (optional, read the manifest)

**`list_feature_types()`**, **`list_metrics()`**, **`describe_feature_type(name)`** return the
curated capability menu so the agent can *show* its exploration. They are optional — for a
curated question the manifest is already in the system prompt — but they keep the "agent figures
it out" narrative available, and they are the seam where richer live discovery would later attach.

---

## 7. Capability discovery and the curated manifest

The agent cannot compose a valid query unless it knows which collections, datasets, fields, and
*values* it may query by. We checked how discoverable that is across the three sources, and the
answer shaped a decision.

**Discovery surfaces exist, but they are heterogeneous and uneven:**

- **ArcGIS** is the cleanest — layer metadata (`?f=json`) lists fields, and `returnDistinctValues`
  enumerates a field's values.
- **Nomis** is programmatic but deeply nested and vintage-sensitive: `def.sdmx.json` → datasets →
  dimensions → codes, with geography `TYPE` codes that differ per dataset.
- **OS NGD** lists collections live (`/collections`), but allowed attribute **values** come
  largely from **documented code lists** (e.g. the `sitedescriptionvalue` list), not a uniform
  per-collection value endpoint.

There is no single "ask the API what I can query" call. So:

**Decision: a curated capability manifest, plus optional discovery tools.** v0.1 ships a small,
hand-verified registry — the collections, datasets, fields, geography vintages, and value
vocabularies the demo actually uses — injected into the system prompt as the agent's menu. The
manifest maps friendly names the agent reasons about (`population`, `health_centre`,
`local_authority`) to the exact upstream specifics (`NM_2021_1` + TYPE154 + pinned dimensions;
`lus-fts-site` + `description='Health Centre'`; the LAD BGC service URL). Adding a capability is
adding a manifest entry. The optional discovery tools ([§6](#discovery-tools-optional-read-the-manifest))
let the agent enumerate that menu on the trace when it is useful to show.

This keeps every curated query valid and fast, while being honest that it is a scaffold. The
general problem — letting the agent reliably navigate the *full, unbounded* parameter space
(thousands of Nomis datasets, every NGD attribute and value, vintage mismatches) at runtime — is
a real open challenge, logged in [§12](#12-open-questions-for-the-build-phases).

---

## 8. Data flow and streaming

**The event-sink seam.** The agent loop does not know whether it is talking to a terminal or a
browser. It emits structured events to an abstract `EventSink`. A `CliSink` prints a readable
trace; an `SseSink` serialises events onto an HTTP stream. This is the seam that lets build
phase 1 ship and test the whole agent from a CLI, and build phase 2 wire the *identical* loop to
the browser by swapping the sink.

**Event types** (each an SSE `event:` with a JSON `data:` payload):

| Event | Payload | Meaning |
|---|---|---|
| `status` | `{state}` | agent is thinking / calling a tool / done |
| `message` | `{text}` | streamed assistant reasoning between tool calls |
| `tool_call` | `{id, name, input}` | the agent invoked a tool — the trace entry |
| `tool_result` | `{id, descriptor}` | the small handle descriptor (never the data) |
| `view` | `{kind, handle, encoding}` | a render instruction for the frontend |
| `error` | `{message, tool_id?}` | a tool or model error, surfaced not swallowed |
| `done` | `{summary}` | the agent's closing answer |

**HTTP surface (build phase 2):**

- `POST /api/query` with `{question}` → a `text/event-stream` response (FastAPI
  `StreamingResponse`) carrying the events above.
- `GET /api/datasets/{handle}` → the full GeoJSON or table JSON for a handle, for the browser to
  render. This is how heavy geodata reaches the map without passing through the model or bloating
  the SSE stream.

**A query's life:** the browser POSTs a question and opens the stream → the agent loop runs,
emitting `tool_call`/`tool_result` pairs the chat pane renders live → a `view` event tells the
map or chart what to draw → the browser GETs the named handle and renders it → `done` carries the
written answer.

---

## 9. The analytical core

The one analytical capability, done well: **spatial aggregation with normalisation.**

1. `aggregate` performs the spatial join — features into boundary polygons — with shapely /
   geopandas. Containment runs in WGS84; metric variants reproject to EPSG:27700 first.
2. `normalize` joins the aggregate to a statistic on the GSS code and computes a ratio or a scaled
   rate.
3. The result is both a `TableDataset` (the ranked bar chart) and, via `join_to_boundaries`, a
   `GeoDataset` (the choropleth). Both outputs are first-class, as the brief insists.

This is deliberately one class of question executed reliably, not a general spatial engine. The
extension path to buffers, proximity, and network analysis is *new compute tools the agent
composes with the existing fetch tools* — not a rewrite.

---

## 10. Deployment posture

One FastAPI process serves the API, the SSE stream, and the built static frontend. Keys are
environment variables (`ANTHROPIC_API_KEY`, `OS_API_KEY`); Nomis and the ArcGIS services need no
key. The same artifact runs locally under `uvicorn` and in a container when deployed. No auth.

**The one real risk no-auth deployment opens:** OS NGD is a **premium API** (a £1,000/month free
transaction allowance), and a public, unauthenticated app that proxies the presenter's key on
every request invites abuse and could burn that allowance. This is not solved in v0.1, but it is
named: the mitigations are a simple per-IP rate limit on `/api/query`, a transaction cap, and/or a
separate capped demo key. Tracked in [§12](#12-open-questions-for-the-build-phases).

**Single-instance state:** the in-memory `DatasetStore` ties a session to one process. Fine for
local use and a single deployed instance; horizontal scaling would need a shared store (Redis or
disk). Out of scope for v0.1.

---

## 11. The feasible-question envelope

The 100-feature-per-page ceiling on OS NGD is a hard architectural constraint, and it splits the
question space cleanly. The architecture supports both classes with the same tools; only the
scale differs.

- **National, statistic-by-boundary** — e.g. *deprivation by local authority*, *population by
  local authority*. All from ONS / ArcGIS (~309 LAD features, joined by GSS code). Fast and
  robust. Skips `fetch_features`/`aggregate`. This is the **safe fallback** for a live stage.
- **Regional, feature-aggregation** — e.g. *health-centre provision per 10,000 residents by
  local authority across Greater Manchester*. Exercises the **full** chain, but only within a
  bounding box where OS NGD's paging stays bounded. This is the **headline** capability.

Curating the demo question bank within this envelope — a sparse feature type and a bounded region
for the headline, with the national choropleth as a fallback — is what keeps the live demo
reliable. The exact headline question stays a day-of choice, per the brief's "bank, not a locked
question."

---

## 12. First-slice scope — what build phase 1 delivers

Per the brief's backend-first ordering, **build phase 1 is the backend, tested from a CLI against
live APIs. No UI.** The frontend, SSE endpoint, and visual rendering are build phase 2 — wiring
the *same* agent loop to a browser by swapping the event sink.

**Build phase 1 delivers:**

1. **Source clients** — `os_ngd`, `nomis`, `arcgis`: thin HTTP wrappers that handle auth, paging,
   `outSR`, and CSV/GeoJSON parsing.
2. **The data model and `DatasetStore`** — `GeoDataset`, `TableDataset`, `DatasetDescriptor`,
   handle storage with TTL.
3. **The v0.1 tool catalog** ([§6](#6-the-tool-catalog-v01)) — fetch, compute, and render tools,
   registered in the tool registry. In phase 1 the render tools emit view instructions the CLI
   prints and write their dataset to disk.
4. **The hand-rolled agent loop** emitting events to a `CliSink`.
5. **The capability manifest** — the curated registry, injected into the system prompt.
6. **A CLI harness** — `python -m surveyor "question"` — that runs a curated question end-to-end
   against **live** APIs and prints the legible tool-call trace.

**Acceptance for build phase 1:** the headline chain
`fetch_boundaries → fetch_features → aggregate → fetch_statistic → normalize → render_*`
runs live from the CLI for the worked example (*health-centre provision per 10,000 residents by
local authority across Greater Manchester*), the trace is readable, and the national stat-only
fallback (population or deprivation choropleth by LAD) also runs.

### Proposed file layout

```
surveyor/
  pyproject.toml              # fastapi, uvicorn, anthropic, httpx, shapely, geopandas, pyproj, pydantic
  .env.example                # ANTHROPIC_API_KEY, OS_API_KEY
  README.md
  app/
    main.py                   # FastAPI app, routes, static mount  (phase 2)
    config.py                 # settings from environment
    cli.py                    # `python -m surveyor "question"`     (phase 1 entrypoint)
    agent/
      loop.py                 # the hand-rolled Anthropic tool loop
      prompt.py               # system prompt + manifest assembly
      events.py               # EventSink, CliSink, SseSink, event types
    tools/
      registry.py             # tool registration + schema export
      base.py                 # Tool protocol, ToolResult/descriptor types
      fetch_boundaries.py
      fetch_statistic.py
      fetch_deprivation.py
      fetch_features.py
      aggregate.py
      normalize.py
      join.py
      render.py
      discover.py             # optional discovery tools
    sources/
      os_ngd.py
      nomis.py
      arcgis.py
    data/
      store.py                # DatasetStore
      models.py               # GeoDataset / TableDataset / descriptors (pydantic)
      crs.py                  # pyproj reprojection helpers
    manifest/
      capabilities.py         # the curated registry
  web/                        # thin static frontend                 (phase 2)
    index.html
    app.js                    # SSE client + chat trace
    map.js                    # MapLibre GL choropleth / points
    chart.js                  # ranked bar
    styles.css
  tests/
    fixtures/                 # captured real API responses (real shapes, per testing policy)
    test_sources_*.py
    test_tools_*.py
    test_agent_loop.py
  scripts/
    dev.sh
```

---

## 13. Open questions for the build phases

1. **Capability discovery at scale** *(the logged challenge)* — the curated manifest is a v0.1
   scaffold. How does the agent reliably navigate the full, unbounded parameter space — thousands
   of Nomis datasets, every NGD attribute and value, geography vintage mismatches — at runtime?
   Candidate directions: live discovery tools backed by retrieval over cached schemas; a semantic
   index of datasets; a "propose then validate against queryables" step. Worth a follow-up issue.
2. **Caching vs. honest latency** — the brief commits to no caching ("latency is honest
   behaviour"). Nomis and ArcGIS publish no SLA, and a live on-stage call can hang. Is a thin
   response cache or a pre-warm step worth it for stage robustness, and does that betray the
   principle or just de-risk the demo?
3. **The paid-key exposure** — what is the minimum viable rate limit / cap for a public no-auth
   deployment that proxies the OS NGD key? (See [§10](#10-deployment-posture).)
4. **Sub-LAD scaling** — LSOA-level questions exceed Nomis's 25k-cell anonymous cap and ArcGIS's
   single-page limit. v0.1 stays at LAD/MSOA; LSOA needs pagination, tiling, or a Nomis `uid`.
5. **Basemap** — MapLibre GL with a free style (no key) versus the OS Maps API (a key and a
   proxy). Decide in build phase 2.
6. **Chart library** — Observable Plot vs. Chart.js for the ranked bar. Thin either way; defer.
7. **Wrong-answer handling** — the agent will sometimes return spatially or statistically
   misleading results. Transparency helps but does not solve it. Deferred to the product phase,
   per the brief.
