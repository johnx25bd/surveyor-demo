# Phase 5 — review notes

Build phase 2 (the browser UI) was reviewed in three parallel passes — **security & robustness**, **simplicity & efficiency**, and **design fidelity, UX, accessibility & documentation** — against the architecture's intended posture (`docs/02-architecture.md` §11: single-instance, no auth, "honest latency", OS NGD as a metered key). This records what they found and what we did about it, so the trail is durable.

The headline: the build is a faithful, correct port for the **local single-user demo**. The gaps are (a) public-deploy hardening the architecture already flagged as unsolved, plus two it didn't; (b) real accessibility and UX wins; and (c) bundle size. None block the demo; all are worth doing before a public deployment.

## Fixed

### Security & robustness ([PR #17](https://github.com/johnx25bd/surveyor-demo/pull/17))

- **Open path proxy.** The basemap catch-all was effectively a keyed reverse proxy to *any* path on `api.os.uk` the key is entitled to, and `..` could escape the vector-tile base. Now allow-listed to the `vts` prefix.
- **Key-strip is now belt-and-suspenders.** Alongside the `?key=` denylist strip, a positive check withholds any response in which the real key value survives.
- **Bounded input & concurrency.** The `question` is bounded (1–2000 chars, non-blank); oversized bodies are rejected before they're read (413); concurrent live runs are capped (429 over the cap) so a burst can't fan out unbounded metered-API spend.
- **No error-detail leakage.** The unexpected-error path logs detail server-side and returns a generic message (the exception string could carry internal paths or a keyed URL).
- **Security headers.** `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`.

### Frontend polish, accessibility & simplification ([PR #18](https://github.com/johnx25bd/surveyor-demo/pull/18))

- **Bundle split.** Lazy-load MapPane + vendor chunks: initial JS **1.13MB → ~150KB**.
- **Accessibility.** Chat auto-scrolls inside an `aria-live` region; ranked rows are keyboard-operable with a focus ring; `prefers-reduced-motion` honoured; the subtle grey darkened to clear WCAG AA; `type=button` on the expander/send.
- **UX.** The silent keyless-basemap fallback now explains itself; MapLibre controls restyled to the OS language; a basic responsive story; long-token wrapping; height-capped composer; the rail shows a skeleton (not the empty state) while a chart's table loads.
- **Simplification.** One shared `classify()` pipeline (was duplicated across map and chart); `removeFeatureState` replaces hand-tracked hover/select bookkeeping.

### Earlier in the build

- Markdown answers render (were dumping raw markdown); the choropleth draws without an OS key (the keyless style document loaded but its tile source 503'd, stalling the style); the ranked-value column was widened for real magnitudes.

## Deferred — needed before a public, no-auth deploy

These are the architecture's open question #3 (the metered-key risk) made concrete. Out of scope for the local demo; tracked here so they aren't forgotten.

- **Per-IP rate limiting and auth** on `/api/query`. The concurrency cap is an in-process backstop, not a substitute — a shared secret or real auth is the answer, plus a process-level spend/transaction cap that fails closed. A separate capped demo OS key is the cleanest financial backstop.
- **Cancellable runs.** On client disconnect the agent loop can't be interrupted mid-step; it runs to completion (capped at `MAX_STEPS`) even with no listener. A cancellation flag the loop checks between steps would stop abandoned runs from spending the key.
- **Session-keyed dataset store.** The in-memory `DatasetStore` is shared process-wide; multi-user use should key it by session (the architecture says as much, §11).
- **Content-Security-Policy.** Worth adding (start report-only — MapLibre uses blob workers and GitHub-hosted sprites) as a second layer behind the markdown sanitisation.

## Deferred — low priority / polish

- The `night.json` basemap stylesheet is a leftover (the `night` theme maps to `dark.json`); remove it.
- The empty-state "JD" account avatar implies auth that doesn't exist.
- `done.summary` is computed by the backend but unused by the UI (the step-ceiling path's friendlier sentence is dropped in favour of the raw error).
- The vendored `surveyor.css` carries `drawer`/`timeline` tool-call styles the React port never renders — only `inline` is wired.

## Not changed (verified correct)

The sync-loop → async-SSE bridge, the StrictMode double-mount handling, the live-value refs and once-bound map handlers, the styledata re-add after a basemap swap, the static-mount ordering (`/api/*` wins), the markdown HTML sanitisation (react-markdown default), and the popup escaping are all correct for the intended posture and were left alone.
