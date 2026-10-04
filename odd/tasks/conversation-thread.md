# Conversation thread in the UI

## Objective

Make the multi-turn session visible: the main area shows the session's turns as a thread
(user message + estimate), and the form becomes a follow-up composer after the first turn.

## Problem / why

Multi-turn already works on the server (same `session_id`, history window replayed), but the UI
replaces each estimate with the next one, keeps the previous text in the form and its copy reads
as a one-shot task, so users believe they can only estimate once. Switching sessions restores only
`last_estimate`.

## Scope

- In: the session keeps a display record per turn (description as typed, attachment names,
  estimate, prompt_version, cache_hit, created_at), capped by the same window as the history;
  `GET /sessions/{id}` returns `turns`; the UI renders the thread, clears the composer after a
  successful send, switches copy to follow-up mode, rebuilds the thread when switching sessions.
- Out: persistence (Redis), turns beyond the window, editing/deleting turns, streaming.

## Constraints

- AGENTS.md layer rules; `web/src/api/types.ts` mirrors `app/schemas/`.
- The rendered user prompt in `ConversationHistory` stays the LLM's history; the display record
  is separate data (what the user typed), not a re-parse of the prompt.
- Copy button, memory panel, sessions list from earlier work keep working.
- No commits unless the user asks. TDD: off. Runners: `uv run pytest`, `pnpm test:web`.

## Tasks

- [x] T1 — Backend: display turns on `Session` (same cap as the window), `turns` in `SessionDetail`
  (keep `last_estimate` for compatibility or drop it if the UI was its only consumer), tests.
- [x] T2 — UI: thread state in `useSession` (append on success, rebuild on select/resume),
  thread rendering (user bubble + `EstimationResult`-style card per turn, loading card for the
  pending turn, errors inline), composer reset + follow-up copy (es/en), tests.
- [x] T3 — Docs: README/AGENTS mention of the thread and `turns`; update this document.

## Acceptance criteria

- Two sends in a row show two turns in order; the composer is empty after each success and keeps
  project type / detail / format.
- Switching to another session shows its kept turns; switching back restores them.
- After a reload the active session's thread is restored.
- A failed send keeps the typed text and shows the error without losing earlier turns.

## Checks

`uv run pytest`, `pnpm exec vitest run`, `pnpm exec tsc -b`, `pnpm lint` (Node 24), browser check.

## Progress

- T1–T3 implemented (not committed): `Session.turns` of `TurnRecord` (trimmed with the history window), `SessionDetail.turns` replaces `last_estimate`, thread UI (`ConversationThread`, per-turn `EstimationResult`), composer reset via `resetKey` + follow-up copy, docs.
- Evidence: `uv run pytest` (x2) all pass; `pnpm exec vitest run` 9 files / 97 tests pass; `pnpm exec tsc -b` clean; `pnpm lint` clean.
- Open: browser check not run by the writer; follow-ups still need >= 20 chars (server `transcript` min_length); `cache_hit` is always false for session turns; client-side thread can exceed the server window until reload.

- Feature document created; T1–T3 delegated to one writer.
- Parent check: `uv run pytest` all pass. Browser check (stubbed estimate endpoint, no LLM spend):
  two follow-ups append as separate turns in order, composer clears and switches to follow-up copy
  ("Send"), the new turn scrolls into view, memory panel updates per turn. Observed edge: text typed
  before the session is created is lost, because `EstimateForm` remounts on `key={session.id}`.
