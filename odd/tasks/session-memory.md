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
- [x] T3 — `POST /sessions/{session_id}/estimate` (multipart: `transcript` + typed form fields +
  `attachments`) with path B (local extraction, `pypdf` + `python-docx`) in
  `services/attachments.py`; `get_safe_session_request` runs extraction + guardrails on the
  combined text; `AttachmentError` → 400, `SessionNotFoundError` → 404; README section. Route:
  inline. (Reordered to follow the course: attachments before memory.)
- [x] T4 — `project_metadata` in the system prompt (`v3/project_metadata.j2`, trailing block, empty
  tags on the first turn; no v4 by user decision) + LLM extractor (`services/metadata_extractor.py`,
  prompt `prompts/metadata/v1/`) updating it after each turn. Session turns skip the caches.
  `ProjectMetadata` moved to `schemas/sessions.py` (the loader needs it). Route: inline.
- [x] T5 — History window replayed to the LLM: default 6 turns, `to_messages_list(system)`,
  `ChatLLMProvider.complete_messages` (LiteLLM `complete()` delegates to it),
  `EstimationService.prepare_session_turn` → `SessionTurn` (history keeps transcript +
  `[attachments: ...]` reference, PII-redacted). Route: inline.

## Checks

- `pnpm test:api`

## Progress

- T1: done, commit `f72cd4b`. 8 tests in `tests/test_sessions.py`.
- T5: done. 8 new tests (`test_session_history.py`, history + provider); 314 passed.
  The user should set `SESSION_MAX_TURNS=6` in `.env.example` if it still says 10.
- T4: done, commit `7ff3a2d`. 11 tests in `tests/test_project_metadata.py`; `uv run pytest` 306 passed.
  Injection check exposed as `prompt_injection_pattern()` in `guardrails/input.py`.
- T3: done, commit `cb09560`. 20 tests in `tests/test_attachments.py`; `uv run pytest` exit 0. Limits
  are module constants (5 files, 5 MB each, 60k chars). Single-turn for now: history/metadata in T4.
- T2: done, commit `a5b3dfa`. 2 route tests; `uv run pytest` exit 0. `SESSION_MAX_TURNS` added to
  `config.py` (the user added it to `.env.example`). The conftest `client` now overrides the store
  with a fresh `session_store` fixture per test.
- Commits: only when the user asks.
