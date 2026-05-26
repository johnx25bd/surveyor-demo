# Surveyor — Concept Brief

*Output from [this Claude.ai conversation](https://claude.ai/share/5d9ab597-1e94-4580-b890-11bfcd8b4d71).*

## What we're building

Surveyor is an agentic interface to UK national geospatial datasets: a chat-driven tool where natural language questions are translated by an LLM agent into live queries against Ordnance Survey and Office for National Statistics APIs, with results visualised on a map and in charts. Every step the agent takes — which dataset it chose, which filter it composed, which spatial operation it ran — is visible to the user, so the answer can be checked rather than trusted blindly.

## Why this fits the audience

The workshop runs at Geovation, Ordnance Survey's location data innovation hub in central London, for an audience of technical and semi-technical founders and members. They know the gap between "I have a spatial question" and "I have a defensible answer" first-hand. The historical answer to that gap has been days of work: hand-coding WFS filters, wrangling CRS mismatches, scripting joins in Python, building one-off visualisations. Surveyor collapses that pipeline into a conversation while keeping the work inspectable — which matters more to this audience than to a general one, because they know what would normally be hidden.

The workshop narrative is process over product. The point is not to unveil a finished tool but to show how far an agentic stack with Claude Code can take a real, useful idea in a few hours. Surveyor is the vehicle; the build process is the lesson.

## The user (distinct from the workshop audience)

Deliberately broad: anyone who would benefit from a spatial answer to a national-scale question. Policy people, founders, journalists, researchers, curious citizens. The bet is that the surface area of "people who need spatial answers" is much larger than the surface area of "people who can write WFS filters." Surveyor is for the gap between those two.

## Scope — in for v0.1

**Geographic scope:** Great Britain (national). Not constrained to a single city or region. The agent passes whatever bounding box or geography filter is appropriate to the question.

**Data sources:** Two, live, no caching.

- Ordnance Survey NGD Features API (built environment features)
- Office for National Statistics — Nomis for statistics, ONS Geography Portal for boundaries
- (MHCLG IMD via the Open Geography Portal is in scope if it's needed for a candidate question — it lives in the same ArcGIS REST surface as ONS boundaries.)

**Analytical capability:** One class of question, done well — *spatial aggregation with normalisation*. The agent can fetch features, fetch boundary polygons, fetch a statistic by geography, aggregate features into polygons (count or sum), and normalise by the statistic. This unlocks questions of the form "where in England is X most concentrated relative to Y, by Z geography?"

**Outputs:** Map render (choropleth and/or point layer) and chart render (at minimum, a ranked bar chart). Both are first-class — the principle that spatial and non-spatial outputs both belong is part of the pitch.

**Transparency:** Every tool call the agent makes is visible in the chat pane, with inputs and outputs inspectable. This is structural, not cosmetic — it follows from the agent loop architecture, not from a UI decision.

**Candidate demo questions (a bank, not a single locked question):**

- Where in England is deprivation high but green space provision low, by local authority?
- Where are the largest populations relative to the count of GP surgeries, by LSOA?
- Which local authorities have the highest density of listed buildings per capita?
- Compare the count of [building type] across major English cities.

The intent is to have several candidates ready and pick on the day based on what's working and what reads the room.

## Scope — out for v0.1

- Network analysis (isochrones, routing, travel-time catchments) — deferred to v0.3.
- Buffer and proximity queries ("within 500m of...") — deferred to v0.2 unless trivial to include.
- Additional data sources (HM Land Registry, environmental, transport) — deferred to v0.2.
- Multi-step or memory-bearing conversations ("now do the same for Wales") — deferred to v0.4.
- Saved sessions, shareable links, exports — deferred.
- Deployment beyond local. The workshop demo runs on the presenter's laptop; the repo is public on GitHub. Public deployment is explicitly out of scope for v0.1 because it introduces auth, CORS, and environment complexity that detracts from the build narrative.
- Caching of any kind. All API calls are live at query time. Latency is treated as honest behaviour of the system, not something to hide.

## Build sequence — backend first

A deliberate ordering choice: v0.1 is built backend-first, with the UI as a thin visualisation layer over a tested agent. The reasons:

1. The hard part is the agent and its tool surface. If the tools work and the agent reasons over them correctly, a usable UI follows in less time than the inverse.
2. UI design decisions are better made once the agent's actual behaviour is visible. Designing the chat pane in detail before watching real tool calls stream in is premature optimisation against an imagined system.
3. The "show your work" principle is more credible as a structural property of a working agent than as a UI claim. Building the agent first and exposing it through the UI second is the honest order.

Concretely, the build phases after this brief are:

1. Architecture and tool design.
2. Backend build: tool implementations against live OS and ONS endpoints, agent loop, tested from a CLI.
3. UI build: three-pane layout (chat, map, charts) wired to the working backend, with design decisions informed by observed agent behaviour.

UI specifics — chart pane behaviour, tool call display, empty state, layer management — are deferred to the UI build phase. The brief commits to the three-pane shape (chat left, map right, charts present) and the "show your work" principle; it does not commit to interaction patterns that are better decided with a working agent in hand.

## Open questions for design and architecture

**Architecture phase:**

- Tool surface granularity: how fine-grained should the tool API be? One `query_os_ngd` tool, or one tool per NGD collection? Trade-off between agent flexibility and prompt clarity.
- Streaming UX: how are tool calls and partial results streamed to the frontend? SSE vs WebSocket vs polling.
- CRS handling: is reprojection an explicit tool the agent chooses, or implicit in the data fetch tools? Affects how visible CRS work is in the "show your work" view.
- Where does the agent live: server-side Python with the Anthropic API, or some other shape?
- What does a tool "render" call actually do — push state to the frontend, or return data the frontend chooses how to display?

**Design phase:**

- How are tool calls visualised in the chat pane? Collapsible blocks? Inline reasoning? A separate "agent activity" stream?
- Does each new query replace or append map layers and charts? Single-result mode vs session-accumulating mode.
- Empty state: what does a user see before typing? Suggested questions? Documentation? Blank?
- Map legend, layer controls, feature inspection — what's in v0.1 vs deferred?
- How does the user know when the agent is done versus still working? Latency could be ten-plus seconds for some queries.

**Product phase (post-demo):**

- What does "wrong answer" handling look like? The agent will sometimes return spatially or statistically misleading results. The transparency principle helps but doesn't fully solve.
- How are dataset limitations surfaced (small-area suppression, boundary changes, attribute completeness)?
- Is there a path from v0.1's "ask and see" to v0.4's analytical dialogue, or are those different products?

## What this brief honestly does not decide

The visual design of the application. The specific interaction model for the chat pane. The exact list of OS NGD collections used in v0.1. The cloud architecture (because there isn't one — v0.1 runs locally). The headline demo question (we have a bank of candidates and will pick on the day). These are all deliberate non-decisions, deferred to the phases where they belong.