# Session memory and attachments (session 05)

## Objective

Turn the estimator from a one-shot transaction into a multi-turn conversation: a session keeps a
sliding window of the conversation plus the project facts (`project_metadata`), and estimate
requests can carry PDF/Word attachments.

## Scope

- In: `POST /sessions`, in-process sliding-window history, `ProjectMetadata` injected into the
  system prompt, `POST /sessions/{session_id}/estimate` (multipart), PDF/Word attachments.
- Out: cumulative/anchor summaries, dynamic tier, persistence across restarts, web search,
  function calling, Actor-Critic-Boss.

## Constraints

- Layer rules from `AGENTS.md`: no FastAPI in services, `litellm` only under `services/llm/`.
- The system prompt is rendered per request (cacheable static prefix + trailing blocks), so it is
  never stored in the history; `project_metadata` goes in a trailing block.
- `.env.example` is not readable/writable by the agent: new settings are listed here for the user.

## Tasks

- [x] T1 — Session state model: `app/services/sessions.py` (`ConversationHistory`,
  `ProjectMetadata`, `Session`, `SessionStore`) + `SessionNotFoundError` + tests. Route: inline
  (2 small files, design agreed in chat).
- [x] T2 — `POST /sessions` → 201 `{"session_id"}` (`routers/sessions.py`, `schemas/sessions.py`, `get_session_store` with `lru_cache`, `SESSION_MAX_TURNS` setting). Route: inline.
- [ ] T3 — `project_metadata` in the system prompt
- [ ] T4 — `POST /sessions/{session_id}/estimate` (multi-turn)
- [ ] T5 — Attachments (PDF/Word)

## Checks

- `pnpm test:api`

## Progress

- T1: done, commit `f72cd4b`. 8 tests in `tests/test_sessions.py`.
- T2: done. 2 route tests; `uv run pytest` exit 0. `SESSION_MAX_TURNS` added to
  `config.py` (the user added it to `.env.example`). The conftest `client` now overrides the store
  with a fresh `session_store` fixture per test.
- Commits: only when the user asks.
