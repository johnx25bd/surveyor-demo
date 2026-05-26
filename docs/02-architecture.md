# Surveyor — Architecture

This document makes the binding technical decisions for Surveyor v0.1: the language and
runtime, the agent loop, the tool and operation interfaces every data source and capability plugs
into, the data model, how a question becomes a map and a chart, the file layout, and the scope of
the first build slice. It is written so a coding agent could scaffold the project from here
without further architectural input.

Inputs: [`00-idea.md`](00-idea.md) (the concept) and [`01-ui-mockup.md`](01-ui-mockup.md) (the
three-pane shell). Those documents are *intent*, not specification — the stack, tool surface,
data models, and interfaces below are designed here from first principles.

**Grounded in real responses.** Every API shape, field name, parameter, and limit below was
captured from a **live call** to the upstream API while writing this — not read from
documentation. The captured shapes (Nomis population, ArcGIS boundaries, ArcGIS IMD, OS NGD
`lus-fts-site-2` features, and a working OS NGD CQL filter) are the contract the data models are
built against, and become the test fixtures for build phase 1.

---

## 1. Architecture at a glance

Surveyor is a single deployable web application. A Python backend runs an LLM agent that
translates a natural-language question into a sequence of tool calls against live UK geospatial
and statistics APIs, composes analytical operations over the results, and emits render
instructions. A thin frontend renders the streamed agent trace, a map, and a chart. Every tool
call is visible because the agent loop emits it — transparency is a structural property of the
loop, not a UI affordance.

```
                          ┌───────────────────────────────────────────────┐
  Browser (thin client)   │  FastAPI app  (single deployable unit)         │
  ┌───────────────────┐   │                                                │
  │ chat trace        │   │  POST /api/query  ──►  Agent loop              │
  │ map (MapLibre)    │◄──┼── SSE event stream     (Anthropic SDK,         │
  │ chart             │   │                         hand-rolled)           │
  └───────────────────┘   │                           │                    │
        │  GET /api/datasets/{handle}                 │ calls tools        │
        └────────────────►│                           ▼                    │
                          │  Registry ─► fetch · analysis · render tools   │
                          │        │                  │                    │
                          │        ▼                  ▼                    │
                          │   Source clients     DatasetStore (handles)    │
                          └────────┼────────────────────────────────────── ┘
                                   ▼
              OS NGD Features API · ONS Nomis API · ONS/MHCLG ArcGIS services
                              (live, server-side, keys never reach the browser)
```

The load-bearing ideas, each justified below:

- **Operation-granular tools** ([§4](#4-the-tool-interface)) — one tool per logical step, so the
  trace reads as a sequence of comprehensible actions and the extension story is "add a tool,
  register it."
- **Dataset handles** ([§4.2](#42-dataset-handles--the-idea-underneath)) — tools exchange small
  server-side references, never raw geodata through the model's context.
- **A composable analytical operation set** ([§7](#7-the-analytical-operation-set)) — the analysis
  layer is typed dataset→dataset operations the agent recomposes, not one hard-wired pipeline.
- **An event sink the loop writes to** ([§10](#10-data-flow-and-streaming)) — the same agent loop
  drives a CLI trace (build phase 1) and a browser SSE stream (build phase 2) by swapping the sink.

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

**Why.** Two factors decide it. First, this runs live on the presenter's laptop, so presenter
fluency and the ability to debug on stage outweigh ecosystem novelty — Python wins decisively
there. Second, the analytical core is spatial work (point-in-polygon aggregation, reprojection,
and the proximity operations the roadmap points toward), and Python's geospatial stack is years
ahead of JavaScript's. The one cost — JavaScript would integrate the frontend more tightly — is
small, because the frontend is deliberately thin and talks to the backend over a simple SSE stream
and one data endpoint.

**Deployment is in scope.** v0.1 has no authentication, but it is designed to deploy, not only to
run locally. FastAPI serves the API, the SSE stream, and the built static frontend from one
process, so the same artifact runs under `uvicorn` locally and in a container anywhere (Fly.io,
Render, Railway). All API keys live server-side as environment variables and never reach the
browser. See [§11](#11-deployment-posture) for the one real risk this opens.

---

## 3. Decision — the agent loop: raw Anthropic SDK, hand-rolled

**Decision: a hand-rolled tool-use loop on the raw Anthropic Python SDK. No agent framework.**

| | **Raw Anthropic SDK** (chosen) | A framework (LangChain, etc.) | Claude Agent SDK |
|---|---|---|---|
| Transparency | Total — nothing is hidden; we emit every step | Abstracted behind the framework | Loop managed for us |
| Dependencies | One SDK | Heavy | Heavier than the job |
| Teachability (this is a workshop) | The loop is the lesson | Framework is the lesson | Less to see |
| Fit for a single-turn analytical query | Exact | Overkill | Built for long-horizon autonomy |

**Why.** "Show your work" is the product. A hand-rolled loop makes the agent's mechanics fully
visible and fully ours to instrument — when the agent calls a tool, *we* decide what gets emitted
to the trace, because we wrote the dispatch. The presenter knows this SDK well, which again matters
for live debugging. And for a workshop, the loop being legible *is* the teaching content; a
framework would hide exactly what the audience came to see.

### 3.1 The loop's operating contract

The loop runs the standard Anthropic tool-use cycle: send the conversation plus the tool schemas;
if the model returns `tool_use` blocks, dispatch each to its handler, append the `tool_result`
blocks, and loop; stop when the model returns a final text answer. Concretely:

- **Step ceiling: `MAX_STEPS = 12`** model turns. The headline chain is ~6 steps, so 12 leaves
  room for self-correction. On reaching the ceiling, emit an `error` event and a closing `message`
  saying the question could not be completed within the step budget, then stop. No infinite loops.
- **Tool errors are recoverable, not fatal.** A tool that raises is caught; an `error` event is
  emitted to the sink; and the exception text is returned to the model as that tool's
  `tool_result` content with `is_error: true`. The model can then adapt on the next turn — narrow
  a bbox, pick a sparser feature type, choose a different metric. The step ceiling bounds total
  attempts, so there is no separate retry counter at the loop level.
- **HTTP discipline lives in the source clients** ([§6](#6-source-clients-and-fetch-tools)):
  per-request timeouts (connect 5s, read 30s) and a single retry on a timeout or 5xx with short
  backoff. A second failure raises and becomes a recoverable tool error per above.
- **The model call streams**; text deltas are emitted as `message` events as they arrive.

---

## 4. The tool interface

This is the heart of the architecture: the shape every data source and every future capability
follows.

**Decision: operation-granular tools.** One tool per logical step, not one mega-tool per source
and not one tool per dataset.

| Granularity | Trace legibility | Extension cost | Agent cognitive load |
|---|---|---|---|
| One mega-tool per source | Poor — one opaque call hides the work | Low | High (huge schemas) |
| **One tool per operation** (chosen) | **Excellent — each call is one step** | **Low — add a tool, register it** | **Low — small, sharp schemas** |
| One tool per dataset/collection | OK | Explodes the surface | High (prompt bloat) |

A trace that reads *"got 10 Greater Manchester LAD boundaries → fetched health-centre sites →
counted per LAD → fetched population → normalised per 10,000 residents → rendered choropleth"* is
the transparency principle made literal. It gives a clean extension rule: **a new data source is a
new `fetch_*` tool plus a source client; a new analytical capability is a new operation
([§7](#7-the-analytical-operation-set)); the agent recomposes existing tools.** Adding one is a
registration, not a refactor.

### 4.1 What a tool *is* (the code contract)

Every tool — fetch, analysis, or render — implements one protocol. Its JSON schema is derived from
a Pydantic input model, so the schema the model sees and the parser share a single source of truth.

```python
class Tool(Protocol):
    name: str
    description: str
    Input: type[BaseModel]            # .model_json_schema() is the tool schema sent to the model
    def run(self, ctx: ToolContext, args: Input) -> ToolOutcome: ...

@dataclass
class ToolContext:
    store: DatasetStore               # read input datasets, write output datasets
    manifest: Manifest                # the curated capability registry (§9)
    sink: EventSink                   # sub-step trace notes ("page 3/5", "reprojected 4326→27700")

@dataclass
class ToolOutcome:
    descriptor: dict                  # SMALL object returned to the model as tool_result content
    view: ViewEvent | None = None     # render tools set this; the loop forwards it to the sink
```

The contract the loop relies on:

- **Fetch and analysis tools** write their output dataset to `ctx.store` and return
  `ToolOutcome(descriptor=descriptor_of(handle))` — the descriptor ([§5](#5-the-data-model)), never
  the data.
- **Render tools** return `ToolOutcome(descriptor={"rendered": true, "handle": h, "kind": ...},
  view=ViewEvent(...))`. They still return a `tool_result` (a minimal acknowledgement, because the
  Anthropic API requires one per `tool_use`), while the actual render instruction rides on `view`.
- **The loop** serialises `outcome.descriptor` as the `tool_result` block for the model, and if
  `outcome.view` is set, emits it to the sink.
- **The registry** builds the `tools=[...]` schema list for the API from each tool's
  `Input.model_json_schema()` and dispatches incoming `tool_use` blocks by `name`.

### 4.2 Dataset handles — the idea underneath

Tools do **not** pass raw GeoJSON through the model's context. A boundary set is megabytes; a
feature pull is thousands of geometries (we measured a single OS NGD site at ~50 attributes plus a
MultiPolygon). Pushing that through the model would be slow, expensive, and would drown the trace.
Instead:

- A server-side **`DatasetStore`** holds the actual data, keyed by an opaque **handle** id.
- A tool returns a small **descriptor** to the model — counts, bounds, CRS, columns, a sample.
- Analysis tools take handle ids in, write a new dataset, and return a new handle.
- `render_*` tools take a handle; the **browser** later fetches the full data via
  `GET /api/datasets/{handle}` to draw it.

The agent reasons over **metadata and handles**; the heavy geodata never enters its context and
never round-trips through the model. The `DatasetStore` is the single source of truth for dataset
contents in both build phases — in phase 1 the CLI may also dump a dataset to disk for inspection,
but that is a sink behaviour, not a second storage path.

---

## 5. The data model

Two dataset shapes, one universal join key, one CRS policy — all pinned to captured responses.

**`GeoDataset`** — a GeoJSON `FeatureCollection`, the CRS it is in, the geometry type, and the
property holding the join key. Note from real data: **both ONS boundaries and OS NGD sites come
back as `MultiPolygon`**, so spatial code and the aggregation step must expect MultiPolygon (and
use a representative point / centroid to assign a polygon feature to a containing boundary).

**`TableDataset`** — rows keyed by GSS code, with one or more named value columns. Statistics and
aggregation results are tables.

**`DatasetDescriptor`** — the small object a tool returns *to the model* (values below are from a
real LAD-boundary fetch):

```jsonc
{
  "handle": "ds_7f3a",
  "kind": "geo",                       // "geo" | "table"
  "count": 309,
  "crs": "EPSG:4326",                  // geo only
  "geometry_type": "MultiPolygon",     // geo only
  "bbox": [-6.4, 49.9, 1.8, 55.8],
  "key_column": "LAD21CD",
  "columns": ["LAD21CD", "LAD21NM"],
  "sample": [{ "LAD21CD": "E06000001", "LAD21NM": "Hartlepool" }]   // geometry truncated
}
```

**The universal join key is the GSS code** (`E06000001`, `E08000003`, …). Boundaries carry it
(`LAD21CD`, `LSOA21CD`), Nomis returns it (`GEOGRAPHY_CODE` / `obs[].geography.geogcode`), and IMD
carries it (`lsoa11cd`, plus `LADcd` for rolling up). Every join pivots on this one key, which is
why it sits explicitly in the descriptor.

**The `DatasetStore`** is session-scoped and in-memory for v0.1: `put(dataset) -> handle`,
`get(handle) -> dataset`, with a TTL so a handle outlives the request long enough for the browser
to fetch it. In-memory means single-instance — acceptable for v0.1, flagged in
[§11](#11-deployment-posture).

### 5.1 CRS policy — explicit on every fetch, invisible as a decision

CRS is an **attribute of every dataset**, not a tool the agent reasons about. The sources disagree
on defaults, so we never rely on a default — every fetch tool requests WGS84 explicitly:

- **OS NGD** — pass `crs=http://www.opengis.net/def/crs/OGC/1.3/CRS84` explicitly. (It does appear
  to default to CRS84, but the doc's own discipline is not to depend on undocumented defaults — we
  request it, exactly as we force `outSR` on ArcGIS.)
- **ArcGIS** — force `outSR=4326`. Defaults are otherwise British National Grid (boundaries,
  EPSG:27700) or Web Mercator (IMD, EPSG:3857 — the service reports the Esri alias `102100`).

So every dataset enters the store in **WGS84 (EPSG:4326)**, ready for the web map. When an analysis
operation needs *metric* geometry — area, density per km², `within_distance` — it reprojects to
**British National Grid (EPSG:27700)** internally via `pyproj`, and that reprojection **surfaces in
the trace** (e.g. *"reprojected features 4326→27700 before distance test"*). Pure point-in-polygon
containment is topologically valid in WGS84 at these scales and needs no reprojection. The agent
never calls a `reproject` tool; the projection is visible in handle metadata, not a decision it
makes.

---

## 6. Source clients and fetch tools

Three thin source clients wrap the upstream APIs (auth, paging, CRS, parsing); four fetch tools sit
on top. Real endpoints and parameters are given so this is buildable. Where a fetch needs upstream
specifics (dataset ids, TYPE codes, collection ids, service URLs), they come from the **manifest**
([§9](#9-capability-discovery-and-the-curated-manifest)), not from the model.

**`fetch_boundaries(geography_level, region)` → GeoDataset**
ArcGIS FeatureServer, `f=geojson`, `outSR=4326`. `geography_level` is `local_authority` for v0.1 (MSOA/LSOA are extensions — one manifest entry each, see [§14](#14-open-questions-for-the-build-phases) #4);
`region` is a **manifest-named region** (`england`, `greater_manchester`, …) that the client
resolves to a `where` clause and/or bbox — the model never emits a raw SQL predicate. Verified:
LAD service returns `MultiPolygon` features with `LAD21CD` / `LAD21NM`; `where=LAD21CD LIKE 'E%'`
yields 309 English LADs. **Paging:** loop `resultOffset += maxRecordCount` (2000) while the
response carries `exceededTransferLimit: true`; stop when it is absent/false.
Service (manifest-pinned): `services1.arcgis.com/ESMARspQHYMw9BZ9/.../Local_Authority_Districts_December_2021_UK_BGC_2022/FeatureServer/0/query`.
Uses **BGC** (generalised, clipped) boundaries; drops to **BSC** only if a wide LSOA extent is ever
requested.

**`fetch_statistic(metric, geography_level, region)` → TableDataset (keyed by GSS code)**
ONS Nomis, no API key. v0.1 ships `metric = population`. The manifest supplies the dataset id, the
geography TYPE for the level, and the pinned dimensions; the client requests **CSV** for a flat,
cheap parse:
`dataset/NM_2021_1.data.csv?geography=2092957699TYPE154&measures=20100&c2021_restype_3=0&select=GEOGRAPHY_CODE,GEOGRAPHY_NAME,OBS_VALUE`.
Verified: returns 309 rows of `GSS code → population`. (TYPE codes are dataset/vintage-specific, so
they live in the manifest, never the model.)

**`fetch_deprivation(geography_level)` → TableDataset (keyed by GSS code)**
IMD 2019 ArcGIS service, `returnGeometry=false`, `outFields=lsoa11cd,IMDScore,IMDDec0,LADcd`.
Separate tool because it is a different source and shape. Verified fields and a real row
(`E01001631 → score 34.131, decile 2, LAD E09000011`). **IMD is keyed on 2011 LSOAs**; v0.1
sidesteps the 2011↔2021 boundary drift by rolling IMD up to LAD via the service's own `LADcd`
field rather than joining at LSOA.

**`fetch_features(feature_type, bbox, max_features)` → GeoDataset**
OS NGD Features API, key in the `key` **header** (`OS_DATA_HUB_KEY`), `crs` requested explicitly,
`bbox` **required**. `feature_type` resolves through the manifest to a `(collection, CQL filter)`
pair — verified live: `lus-fts-site-2` + `filter=description='Health Centre'`. **The type filter
must be applied server-side via CQL** — we confirmed that an unfiltered urban bbox is dominated by
`Private Residential Site` / `Industry And Business Site`, and that even a *specific* type
(`Electricity Sub Station`) exceeds the page cap across Greater Manchester. **Paging:** `limit=100`
is a hard ceiling; `numberMatched` comes back `null`, so the client follows the response's
`links[rel="next"]` href until it is absent or `max_features` is reached. `max_features` defaults
to 2,000 (hard ceiling 5,000); hitting it returns an **over-cap signal to the agent** so it narrows
the bbox or picks a sparser type *visibly*, rather than the system stalling. This ceiling is why
feature aggregation is **regional**, not national ([§12](#12-the-feasible-question-envelope)).

---

## 7. The analytical operation set

The analysis layer is **not a hard-wired pipeline**. It is a small set of typed, composable
operations over dataset handles, each registered as a tool, that the agent sequences to fit the
question. This is what keeps Surveyor from being locked to a single "aggregate then normalise"
chain — and it is the axis along which the product grows.

**The operation contract.** Every operation is a typed `dataset(s) → dataset` function: it declares
the dataset *kinds* it accepts (`geo` / `table`) and the kind it returns, reads inputs from the
store by handle, and writes its output back as a new handle. **A new analytical capability is a new
operation implementing this contract** — the registry exposes it as a tool and the agent can
immediately compose it. No existing code changes.

The v0.1 operation set:

| Operation | Signature | Output | Notes |
|---|---|---|---|
| `filter` | `(dataset, where)` | same kind | Post-fetch refinement. `where` is a **constrained expression over the dataset's own columns** (e.g. `IMDDec0 <= 3`), parsed and validated against known columns — not free SQL and never sent upstream, so it does not reopen the §6 raw-predicate concern. The *primary* feature-type filter is applied server-side at fetch; this refines what's already in hand. |
| `aggregate` | `(features, boundaries, op)` | table (by GSS code) | `op ∈ {count, sum:<field>, mean:<field>}`. geopandas spatial join — each feature assigned to the boundary containing its representative point. Reprojects to 27700 if `op` is metric. |
| `normalize` | `(numerator, denominator, per?)` | table (adds a `rate` column) | Joins two tables on GSS code; writes `rate = numerator/denominator`, optionally `× per` (e.g. `per=10000` → "per 10,000"). |
| `rank` | `(table, by, order, top_n?)` | table | Sort by a named column (e.g. `by="rate"`) and optionally limit — drives the ranked chart and "top N" answers. |
| `relate` | `(features, reference, predicate)` | **kind set by predicate** | `predicate ∈ {within, intersects, within_distance:<m>}`; all three return the matched **features** (geo). `within_distance:<m>` reprojects to 27700 for the metric test. The proximity seed and the extension point toward buffers and catchments — note `within_distance` ships in v0.1 as that seed; richer buffering is v0.2. |
| `attach` | `(table, boundaries)` | geo | Joins a table's columns onto boundary polygons by GSS code — produces the choropleth-ready `GeoDataset` for `render_choropleth`. |

**Worked composition** (the headline question):
`fetch_boundaries(local_authority, greater_manchester)` → `fetch_features(health_centre, bbox=GM)`
→ `aggregate(features, boundaries, count)` → `fetch_statistic(population, local_authority,
greater_manchester)` → `normalize(counts, population, per=10000)` → `rank(by="rate", desc)` →
`attach(ranked, boundaries)` → `render_choropleth(geo, value_column="rate")` +
`render_chart(ranked, value_column="rate")`.

**Extension path.** v0.2 buffer/proximity questions enrich `relate` (or add a `buffer` operation);
multi-statistic questions add a `combine` operation; network analysis adds an operation backed by a
routing service. Each is one new operation against the contract — never a rewrite. That is the
claim the brief makes about extensibility, made concrete.

---

## 8. Render tools and outputs

Two render tools turn a dataset into a view instruction. They do not return data to the model — per
[§4.1](#41-what-a-tool-is-the-code-contract) they return a minimal `tool_result` acknowledgement
and emit a `view` event.

- **`render_choropleth(geo_dataset, value_column, title)`** — a choropleth. The `geo_dataset` is a
  boundary set with the analysis result joined on by GSS code (an `attach(table, boundaries)` step,
  or `aggregate`/`normalize` writing straight onto a geo output).
- **`render_chart(table, value_column, label_column, kind, title)`** — `kind` defaults to a ranked
  bar.

Both map and chart are first-class outputs, as the brief insists. In build phase 1 (no UI), the CLI
sink prints the view instruction and writes the dataset to disk for inspection; in build phase 2
the browser consumes the `view` event and fetches the dataset to draw it.

---

## 9. Capability discovery and the curated manifest

The agent cannot compose a valid query unless it knows which collections, datasets, fields, and
*values* it may query by. We checked how discoverable that is, live.

**Discovery surfaces exist, but they are heterogeneous and uneven:**

- **ArcGIS** is cleanest — layer metadata (`?f=json`) lists fields; `returnDistinctValues`
  enumerates a field's values.
- **OS NGD** — `/collections` lists collections, and the **`/collections/{id}/queryables` endpoint
  is open (no key)** and returns the filterable attributes (verified: 11 for `lus-fts-site-2`,
  including `description`). But the allowed *values* of those attributes come from **documented code
  lists** (e.g. `sitedescriptionvalue`), not a value endpoint.
- **Nomis** is programmatic but deeply nested and vintage-sensitive: `def.sdmx.json` → datasets →
  dimensions → codes, with geography `TYPE` codes that differ per dataset.

So *attributes* are largely discoverable at runtime, but *values* and *cross-source semantics* are
not, uniformly. Therefore:

**Decision: a curated capability manifest, plus optional discovery tools.** v0.1 ships a small,
hand-verified registry mapping the friendly names the agent reasons about to exact upstream
specifics. It is injected into the system prompt as the agent's menu.

```python
# manifest/capabilities.py  (shapes; real values shown)

GEOGRAPHIES = {
  "local_authority": Geography(
      service_url=".../Local_Authority_Districts_December_2021_UK_BGC_2022/FeatureServer/0/query",
      key_field="LAD21CD", name_field="LAD21NM",
      vintage="2021-12 (UK, BGC)", max_record_count=2000,
  ),
}

REGIONS = {
  "england":            Region(where="LAD21CD LIKE 'E%'"),                 # 309 LADs
  "greater_manchester": Region(lad_codes=[ "E08000001", "...", "E08000010" ],  # the 10 GM LADs
                               bbox=[-2.75, 53.32, -1.91, 53.69]),
}

METRICS = {
  "population": Metric(
      source="nomis", dataset_id="NM_2021_1",          # 2021 Census TS001, usual residents
      geography_type={"local_authority": "TYPE154"},   # vintage-specific Nomis TYPE code
      pinned_dims={"c2021_restype_3": 0, "measures": 20100},  # 0 = All usual residents; 20100 = count
      value_column="OBS_VALUE", key_column="GEOGRAPHY_CODE",
  ),
}

FEATURE_TYPES = {
  "health_centre": FeatureType(
      collection="lus-fts-site-2", cql_filter="description='Health Centre'",
      geometry="MultiPolygon", density="sparse",   # safe for regional aggregation
  ),
  # other curated SPARSE civic site types: fire_station, police_station, ...
}
```

Adding a capability is adding a manifest entry (and, for a new source, a client). The optional
discovery tools (`list_feature_types`, `list_metrics`, `describe_feature_type`) read this manifest
so the agent can *show* its menu on the trace; they are stubs over curated data, **not** the
general discovery solution (open question #1).

### 9.1 The system prompt skeleton

`prompt.py` assembles the system prompt from a fixed skeleton plus the manifest menu. The skeleton:

```
You are Surveyor. You answer questions about Great Britain by composing tools over live
OS and ONS data, and you show your work.

Capabilities (you may use ONLY these — do not invent collection ids, dataset ids, or values):
  Geographies: {geographies}      Regions: {regions}
  Metrics: {metrics}              Feature types: {feature_types}  (all sparse civic site types)

How to answer:
  1. Resolve the boundary set (geography + region).
  2. If the question counts/sums features: fetch the feature type (already type-filtered
     server-side) within a region bbox, then aggregate into boundaries.
  3. Fetch any statistic needed to normalise; normalize; rank.
  4. Render a choropleth and a ranked chart, then give a short written answer.
  If no features are needed (a statistic-by-area question), skip fetch_features/aggregate.
  That path is the robust one — prefer it whenever it answers the question.

Constraints:
  - Feature fetches require a bbox and a curated feature type.
  - If a fetch reports over-cap, narrow the bbox or choose a sparser type, and say so in the trace.
```

The unbounded version of discovery — letting the agent navigate the *full* parameter space at
runtime — is a real open challenge (open question #1).

---

## 10. Data flow and streaming

**The event-sink seam.** The agent loop does not know whether it is talking to a terminal or a
browser. It emits structured events to an abstract `EventSink`. A `CliSink` prints a readable
trace; an `SseSink` serialises events onto an HTTP stream. This is the seam that lets build phase 1
ship and test the whole agent from a CLI, and build phase 2 wire the *identical* loop to the
browser by swapping the sink.

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
- `GET /api/datasets/{handle}` → the full GeoJSON or table JSON for a handle, served from the
  `DatasetStore`, for the browser to render. This is how heavy geodata reaches the map without
  passing through the model or bloating the SSE stream.

**A query's life:** the browser POSTs a question and opens the stream → the loop runs, emitting
`tool_call`/`tool_result` pairs the chat pane renders live → a `view` event tells the map or chart
what to draw → the browser GETs the named handle and renders it → `done` carries the written answer.

---

## 11. Deployment posture

One FastAPI process serves the API, the SSE stream, and the built static frontend. Keys are
environment variables (`ANTHROPIC_API_KEY`, `OS_DATA_HUB_KEY`); Nomis and the ArcGIS services need
no key. The same artifact runs locally under `uvicorn` and in a container when deployed. No auth.

**The one real risk no-auth deployment opens:** OS NGD is a **premium API** (a £1,000/month free
transaction allowance), and a public, unauthenticated app that proxies the presenter's key on every
request invites abuse and could burn that allowance. Not solved in v0.1, but named: mitigations are
a per-IP rate limit on `/api/query`, a transaction cap, and/or a separate capped demo key. Tracked
in [§13](#13-open-questions-for-the-build-phases).

**Observability.** Beyond the user-facing event trace, source clients log each upstream call with
its URL (key redacted), status, and duration — so a hung live demo can be diagnosed, and the
"honest latency" story has numbers behind it.

**Single-instance state:** the in-memory `DatasetStore` ties a session to one process. Fine for
local use and a single deployed instance; horizontal scaling would need a shared store (Redis or
disk). Out of scope for v0.1.

---

## 12. The feasible-question envelope

OS NGD's 100-feature-per-page ceiling is a hard constraint, and we confirmed it bites even on a
single specific feature type across a city-region. It splits the question space; the architecture
supports both classes with the same tools, differing only in scale.

- **National, statistic-by-boundary** — e.g. *deprivation by local authority*, *population by local
  authority*. All from ONS / ArcGIS (~309 LAD features, joined by GSS code). Fast and robust. Skips
  `fetch_features`/`aggregate`. The **safe fallback** for a live stage, and the prompt tells the
  agent to prefer it when it answers the question.
- **Regional, feature-aggregation** — e.g. *health-centre provision per 10,000 residents by local
  authority across Greater Manchester*. Exercises the **full** chain, but only within a bounded box
  and on a **sparse** feature type. The **headline** capability.

Curating the demo bank within this envelope — a sparse civic feature type and a bounded region for
the headline, the national choropleth as a fallback — is what keeps the live demo reliable. The
exact headline question stays a day-of choice, per the brief's "bank, not a locked question."

---

## 13. First-slice scope — what build phase 1 delivers

Per the brief's backend-first ordering, **build phase 1 is the backend, tested from a CLI against
live APIs. No UI.** The frontend, SSE endpoint, and visual rendering are build phase 2 — wiring the
*same* agent loop to a browser by swapping the event sink.

**Build phase 1 delivers:**

1. **Source clients** — `os_ngd`, `nomis`, `arcgis`: auth, paging (each source's termination rule),
   explicit CRS, CSV/GeoJSON parsing, timeouts/retry, redacted call logging.
2. **The data model and `DatasetStore`** — `GeoDataset`, `TableDataset`, `DatasetDescriptor`, handle
   storage with TTL.
3. **The tool layer** — fetch tools ([§6](#6-source-clients-and-fetch-tools)), the analytical
   operation set ([§7](#7-the-analytical-operation-set)), render tools ([§8](#8-render-tools-and-outputs)),
   the registry and the `Tool`/`ToolOutcome` contract ([§4.1](#41-what-a-tool-is-the-code-contract)).
4. **The hand-rolled agent loop** with its operating contract ([§3.1](#31-the-loops-operating-contract)),
   emitting events to a `CliSink`.
5. **The capability manifest and the system prompt** ([§9](#9-capability-discovery-and-the-curated-manifest)).
6. **A CLI harness** — `python -m surveyor "question"` — that runs a curated question end-to-end
   against **live** APIs and prints the legible tool-call trace.

**Acceptance for build phase 1:** the headline composition
([§7](#7-the-analytical-operation-set)) runs live from the CLI for the worked example
(*health-centre provision per 10,000 residents by local authority across Greater Manchester*), the
trace is readable, and the national stat-only fallback (population or deprivation choropleth by LAD)
also runs.

### Testing strategy

Per the project's testing rule — design against real output, not handcrafted fixtures:

- **Fixture-replay unit tests** for source-client parsing and each tool, using the **real responses
  captured while writing this architecture** (Nomis CSV/JSON, ArcGIS boundary GeoJSON, ArcGIS IMD,
  OS NGD `lus-fts-site-2` items) checked into `tests/fixtures/`. These run offline and gate CI.
- **A live smoke test** for the headline chain, **gated behind an env flag** (e.g.
  `RUN_LIVE_TESTS=1`) so CI never burns the OS key or hammers the upstreams; run locally before a
  demo.

### Proposed file layout

```
surveyor/
  pyproject.toml              # fastapi, uvicorn, anthropic, httpx, shapely, geopandas, pyproj, pydantic
  .env.example                # ANTHROPIC_API_KEY, OS_DATA_HUB_KEY
  README.md
  app/
    main.py                   # FastAPI app, routes, static mount  (phase 2)
    config.py                 # settings from environment
    cli.py                    # `python -m surveyor "question"`     (phase 1 entrypoint)
    agent/
      loop.py                 # the hand-rolled Anthropic tool loop + operating contract
      prompt.py               # system-prompt skeleton + manifest assembly
      events.py               # EventSink, CliSink, SseSink, event types, ViewEvent
    tools/
      base.py                 # Tool protocol, ToolContext, ToolOutcome
      registry.py             # registration + schema export + dispatch
      fetch/
        boundaries.py
        statistic.py
        deprivation.py
        features.py
      analysis/
        filter.py  aggregate.py  normalize.py  rank.py  relate.py
      render.py
      discover.py             # optional manifest-reading stubs
    sources/
      os_ngd.py  nomis.py  arcgis.py
    data/
      store.py                # DatasetStore
      models.py               # GeoDataset / TableDataset / descriptors (pydantic)
      crs.py                  # pyproj reprojection helpers
    manifest/
      capabilities.py         # GEOGRAPHIES / REGIONS / METRICS / FEATURE_TYPES
  web/                        # thin static frontend                 (phase 2)
    index.html  app.js  map.js  chart.js  styles.css
  tests/
    fixtures/                 # captured real API responses (the contract under test)
    test_sources_*.py  test_tools_*.py  test_agent_loop.py
  scripts/
    dev.sh
```

---

## 14. Open questions for the build phases

1. **Capability discovery at scale** *(the logged challenge)* — the curated manifest is a v0.1
   scaffold. How does the agent reliably navigate the full, unbounded parameter space — thousands of
   Nomis datasets, every NGD attribute and value, geography vintage mismatches — at runtime?
   Candidate directions: discovery tools backed by retrieval over cached schemas (queryables for
   attributes, code lists for values); a semantic index of datasets; a "propose then validate
   against `/queryables`" step. **Worth a follow-up issue.**
2. **Caching vs. honest latency** — the brief commits to no caching ("latency is honest
   behaviour"). Nomis and ArcGIS publish no SLA and a live call can hang. Is a thin response cache or
   a pre-warm step worth it for stage robustness, and does that betray the principle or just de-risk
   the demo?
3. **The paid-key exposure** — minimum viable rate limit / cap for a public no-auth deployment that
   proxies the OS NGD key (see [§11](#11-deployment-posture)).
4. **Sub-LAD scaling** — LSOA-level questions exceed Nomis's 25k-cell anonymous cap and ArcGIS's
   single-page limit. v0.1 wires `local_authority` only; MSOA is one manifest entry away, and LSOA
   additionally needs pagination, tiling, or a Nomis `uid`.
5. **Basemap** — MapLibre GL with a free style (no key) versus the OS Maps API (a key and a proxy).
   Decide in build phase 2.
6. **Chart library** — Observable Plot vs. Chart.js for the ranked bar. Thin either way; defer.
7. **Wrong-answer handling** — the agent will sometimes return spatially or statistically misleading
   results. Transparency helps but does not solve it. Deferred to the product phase, per the brief.
