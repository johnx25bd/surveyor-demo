# Deck skill — source material

Pointer note for a future `.agents` skill that builds slide decks in John's style. This is **not** the skill — it's the trail back to the chats and artifacts the skill should be extracted from.

Backlog: [johnx25bd/.agents#91](https://github.com/johnx25bd/.agents/issues/91) — SKILLS.md "Needed > Act".

## What the skill should cover

**Style + scaffold.**

- **Style layer** — speaker notes as scannable bullets (never prose), one-word eyebrows, equal-height/aligned cards with no orphan wraps, hanging-indent wrapped list text, plain tool-agnostic voice (no Claude-fanboy or corporate-cute copy), flow cues (chips joined by arrows, spectrum lines) over text lists, reveal key items as fragments, less text on-slide with detail pushed to notes.
- **Scaffold layer** — reveal.js project structure, the johnx design-system theme (`theme/johnx.css`), cache-busting the theme link (`?v=N`) while iterating CSS, and the PNG export workflow.

## Source chats

Built and styled across surveyor-demo sessions on 2026-05-26 / 2026-05-27. Transcripts under `~/.claude/projects/-Users-x25bd-code-surveyor-demo/`:

- `a6a60c81-b65b-4589-80d6-9cf0e30d1844` — primary build/style session (also the origin of the `deck-style-preferences` memory)
- `e59d51f5-8d7e-4d91-b5ed-d72ec14d34ad`
- `7c668cc5-43e5-4b52-8da6-9db93132a9a4`
- `65f3b4eb-425a-4b5b-aac7-9127a5d252dd`
- `0f4140db-56f4-4291-8296-0be30540862a`
- `6435b09d-564e-4a47-8d25-4c6d01c7315d`
- `d989d060-37ae-4337-acfb-9a000a5f00e8`

Find a transcript: `find ~/.claude/projects -name '<session-id>.jsonl'`

## Other artifacts

- **Deck source** (reveal.js + theme): `~/projects/standing/build-professional-community/workshops/agentic-workflows/presentation/` — `index.html`, `theme/johnx.css`, `build-timeline.html`, `serve.py`, `lib/`.
- **Slide exports** in this repo: the `v4-*` / `v5-*` PNGs in the repo root (the case study is the surveyor-demo build).
- **Existing memory**: `~/.claude/projects/-Users-x25bd-code-surveyor-demo/memory/deck-style-preferences.md` — generalize and promote into the skill (and likely into `~/.agents/memory/feedback/`) when built.

---

**Session:** 65f3b4eb-425a-4b5b-aac7-9127a5d252dd
