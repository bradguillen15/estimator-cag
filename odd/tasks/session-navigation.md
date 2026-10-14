# Session navigation (in-memory)

## Objective

Let the user list the sessions held by the server and switch between them from the sidebar,
including resuming the active session after a page reload.

## Problem / why

Sessions exist only as `POST /sessions` + `POST /sessions/{id}/estimate`. The UI keeps the id in a
`useRef`: a reload or "New conversation" orphans the previous session on the server with no way
back.

## Scope

- In: `GET /api/v1/sessions` (summaries of sessions with at least one turn, most recent first),
  `GET /api/v1/sessions/{id}` (metadata, kept turns, last estimate), `updated_at` on `Session`,
  sidebar session list, switching sessions, resuming the last active session id from
  `localStorage` (fallback: new session on 404).
- Out: persistence across restarts (Redis), DELETE/rename, full transcript replay (only the
  history window, `SESSION_MAX_TURNS`, is kept, so restore shows the last estimate only).

## Constraints

- AGENTS.md layer rules; `web/src/api/types.ts` mirrors `app/schemas/` in the same change.
- Restored estimate has no `prompt_version`/`cache_hit`: the result renders without meta chips.
- No commits unless the user asks (user rule overrides the ODD per-task commit).
- TDD: off (no project/session configuration). Runners: `uv run pytest`, `pnpm test:web`.

## Tasks

- [x] T1 — Backend: `updated_at` on `Session` (set when a turn is added), `SessionStore.list()`,
  schemas `SessionSummary` / `SessionDetail`, `GET /sessions` and `GET /sessions/{id}` + tests.
  Route: delegated (writer trigger: 3+ non-trivial files).
- [x] T2 — UI: types + client (`listSessions`, `getSession`), `useSession` (`sessions`,
  `selectSession`, resume from `localStorage`), sidebar "Sessions" list + i18n + tests.
  Route: delegated (same writer).
- [x] T3 — Docs: AGENTS.md flow/§6.3 mention of the new endpoints, README if it lists endpoints.

## Acceptance criteria

- `GET /sessions` lists only sessions with turns, ordered by `updated_at` desc.
- `GET /sessions/{unknown}` → 404 via the existing `SessionNotFoundError` handler.
- Clicking a session in the sidebar shows its project memory, turn count and last estimate;
  the next estimate continues that session.
- Reload resumes the last active session when the server still has it.

## Checks

`uv run pytest`, `pnpm test:web`, `pnpm lint`, `tsc -b` (Node 24), browser check of the sidebar.

## Progress

- Feature document created; T1–T2 delegated to one writer.
- T1–T3 done by the writer (no commits). `Session.record_turn` bumps `updated_at`; service uses it.
  Evidence: `uv run pytest` all pass; `pnpm exec vitest run` 9 files / 92 tests pass; `pnpm exec tsc -b` clean;
  `pnpm lint` clean (Node 24).
- Parent spot check: `uv run pytest` failed once on `test_store_list_only_returns_sessions_with_turns_most_recent_first`
  (two `datetime.now()` calls tied, order random). Fixed by pinning timestamps in that test and in the
  `record_turn` test; suite then passed 3/3 runs.
- Browser check (stubbed list/detail endpoints, no LLM spend): Sessions list renders with active row
  highlighted and untitled fallback; selecting a session restores memory, turn count and last
  estimate, and stores `estimator.sessionId` in localStorage.
- Follow-up fix (user report): project memory stayed in English in Spanish chats because the
  metadata extractor never received the response language. New prompt `metadata/v2` (facts written
  in the response language, technology names untouched), `language` threaded service → extractor →
  loader, regression tests at extractor and session-endpoint level. `uv run pytest`: all pass.
