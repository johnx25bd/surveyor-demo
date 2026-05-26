# Phase 2 — UI design intent

A design exploration of Surveyor's interface, built as an interactive mockup
([`01-ui-mockup.html`](01-ui-mockup.html), screenshot in [`01-ui-mockup.png`](01-ui-mockup.png)).
It shows one shell across three app states — empty, mid-query, and result —
worked through a single candidate question: *where in England is deprivation
most concentrated relative to green space, by local authority?*

## What's prominent

- **A three-pane shell**: conversation on the left, map in the center, an
  evidence rail (charts, ranked results, legend) on the right. This is the one
  commitment carried over from the concept brief, and the mockup keeps it fixed.
- **The agent showing its work.** Each step the agent takes appears inline in
  the chat as a labelled tool call — `os.ngd.boundaries.get`, `ons.nomis.query`,
  `os.ngd.features` — so the answer can be inspected rather than trusted. This
  is the heart of the product, so it sits in the primary reading column.
- **The map as the answer surface.** The result state renders a choropleth with
  a linked highlight between map, chart, and chat.

## What's hidden / deferred

- No settings, account, history, or dataset-browser chrome. v0.1 is one
  question class done well; the shell stays out of the way of that.
- The result detail (exact chart encodings, legend design, hover states) is
  sketched, not finalized — enough for the architecture phase to reason about
  surface area, not a finished visual spec.

## What's pluggable

The mockup turns the three things the concept brief left deliberately open into
explicit, live toggles (the "Tweaks" panel):

- **Brand mood** — paper / dark / cartographic.
- **Tool-call presentation** — inline / drawer / timeline. (How prominent the
  "show your work" trace is, versus tucked away.)
- **Chart type** — bar / lollipop / heat-bar for the ranked rail.

These are decisions we don't need to make yet; the mockup keeps them swappable
so the build can defer them.

## Deviation from the concept brief

The brief committed to the three-pane shell and left visual design, interaction
model, and the headline demo question open. The mockup honors the first and
keeps the next two open as tweaks — but it does concretize a **candidate**
demo question (deprivation × green space by local authority) to have something
real to render. That question is illustrative, not yet locked.
