# Session 05 live: compression, evals, Actor-Critic-Boss, audience tier

## Objective

Port the four functional additions of the reference course branch `ai-engineering`
`origin/session_05_live` (estimator/) into estimator-cag, adapted to this codebase's layers
(AGENTS.md), on branch `session_5_live`, one commit per feature.

## Why

A comparison against `session_05_live` showed estimator-cag lacks: history compression (overflowing
turns are hard-deleted in `ConversationHistory.add_turn`, losing commitments such as an NDA or a
frozen budget), an evals harness (no regression signal when prompts/models change), a critic loop
(output checks are deterministic only), and audience-aware output.

## Scope

- In: the four features below, their settings, tests, README/AGENTS updates, `types.ts` mirror for
  any schema field the UI receives.
- Out: UI controls for ACB or tier, persistence of sessions, LLM-based anchor classifier, session
  TTL/eviction, the small session_5 gaps (per-page PDF tolerance, extractor retries).

## Constraints

- Layer rules from `AGENTS.md`: no FastAPI in services, `litellm` only under `services/llm/`,
  env reads only in `config.py`, collaborators injected via `dependencies.py`.
- Keep the static system-prompt prefix cacheable: every new prompt block is a **trailing**,
  conditional block; when a feature is inactive the rendered v3 prompt is byte-identical to today
  (so no prompt version bump).
- Tests never reach a real LLM (`conftest.py` blocks it); fakes only.
- `.env.example` is not readable/writable by the agent: new settings are listed below for the user.
- Commits: Conventional Commits, no AI attribution, run with Node 24 first in PATH
  (`~/.nvm/versions/node/v24.21.0/bin`) so the Husky hook passes. Never `--no-verify`.

## Workflow settings

- TDD: off (no project/session TDD config; source: none). Ordinary functional checks per task.
- Runner: `uv run pytest` (API), `pnpm test:web` + `pnpm lint` + `pnpm build` when `web/` changes.
- RDD: off (global), so no native review.
- Delivery strategy: ask-on-risk; forecast ~1,600 authored lines across 4 commits on one branch.
  Push/PR are the user's decision.

## Tasks

- [x] T1 — History compression. On window overflow the oldest turn pair is peeled off: if the
  user message matches an anchor regex (NDA, signed contract, scope frozen, budget locked/approved,
  compliance/regulatory, hard deadline, contractual, explicit commitment; EN + ES) it is kept
  verbatim in `anchors` (capped, oldest anchor dropped beyond the cap); otherwise it is folded into
  a cumulative LLM summary. Anchors + summary render as a trailing system-prompt block (absent when
  both empty). Summarizer prompt versioned under `app/prompts/`; summary failure keeps the previous
  summary (logged, never fails the turn). Expose `anchors_count` and `summary_chars` in session
  detail (+ `types.ts`). Route: delegated writer (multi-file).
- [x] T2 — Evals harness. `evals/` at repo root: `golden_dataset.json` (≥6 cases covering
  detail/format/language and an insufficient-info case), metrics (schema adherence via the output
  guardrail check, cost/hours bounds parsed from the Markdown total, content recall of expected
  keywords), `run_all_metrics`, CLI `uv run python -m evals.run` (real provider, report to stdout,
  non-zero exit below a threshold). Tests with a fake provider. Route: delegated writer.
- [x] T3 — Actor-Critic-Boss. Critic (cheap model, `CRITIC_MODEL`, falls back to the main chain)
  audits the Markdown estimate and returns structured feedback (verdict accept / needs_iteration /
  reject; issues with category, severity, message); Boss is a pure state machine
  (`BOSS_MAX_ITERATIONS`, default 3) that re-calls the actor with a trailing `critic_feedback`
  block, returning the final estimate plus the iteration trail. New endpoint
  `POST /api/v1/estimate/acb` (input guardrails via `get_safe_request`). Critic failure → accept
  the actor output (logged). Route: delegated writer.
- [x] T4 — Audience tier. Pure regex resolver (precedence: explicit request field > NDA/regulatory
  → executive > ≥2 dev keywords → developer > small team (≤2) → developer... final rule set
  documented in code) returning tier + rule name; trailing `audience` block (absent for `default`).
  Optional `audience` field on estimate + session requests; resolved tier/rule exposed on the
  session detail and estimate responses (+ `types.ts`). Route: delegated writer.
- [x] T5 — Architecture diagram (added by user request). Check whether T1–T4 change
  `docs/architecture/estimation-flow/` (ACB path, compression/tier on session turns); if so update
  `candidate.json` from the code and re-run archify `finalize --repo-root .`, separate commit
  (`docs(architecture): ...`). Route: delegated writer.
- [x] T6 — Frontend: audience + session memory (added by user request, reverses the earlier
  "no UI" scope). Audience selector (auto/default + executive/pm/developer) sent on stateless and
  session estimates; badge showing the resolved audience + rule on each result; session view shows
  anchors count / summary size / last audience. Spanish UI copy, client.ts only for HTTP, Vitest +
  RTL tests. Commit `feat(web): ...`. Route: delegated writer.
- [x] T7a — API: session Actor-Critic-Boss. Revised by user decision (option 1): the UI only uses
  session turns (`client.ts` has no stateless estimate call), so a stateless-only toggle had no
  home. New `POST /api/v1/sessions/{id}/estimate/acb` (same multipart form + guardrails as the
  session estimate) running the Boss loop on the session prompt (history window, anchors/summary,
  metadata, audience) and then recording the turn exactly like a normal session turn (history,
  compression, metadata extraction, `TurnRecord`), returning the session turn fields + final
  verdict + iterations. Commit `feat(sessions): ...`. Route: delegated writer.
- [x] T7r — Rename "ACB"/"Boss" to descriptive names (user decision: the course jargon is not
  self-explanatory). `/estimate/acb` → `/estimate/reviewed`, `/sessions/{id}/estimate/acb` →
  `/sessions/{id}/estimate/reviewed`, `AcbResponse`/`SessionAcbResponse` →
  `ReviewedEstimateResponse`/`SessionReviewedEstimateResponse`, `boss.py`/`Boss` →
  `review_loop.py`/`ReviewLoop`, `BOSS_MAX_ITERATIONS` → `REVIEW_MAX_ITERATIONS`; `critic.py`
  stays. Covers schemas, services, routers, settings, tests, `types.ts`, README, AGENTS.md and the
  archify diagram (also fixes the review box to cover session turns, pending from T7a). Commit
  `refactor: ...`. Route: delegated writer.
- [ ] T7b — Frontend: critic review. `createSessionReviewedEstimate` in `client.ts`, a
  "Revisión con crítico" toggle in the session composer, loading state for the non-streaming call,
  result with final verdict + iteration trail (attempt, verdict, issues by severity). Tests.
  Commit `feat(web): ...`. Route: delegated writer.

## Acceptance criteria

- `uv run pytest` green after every commit; `pnpm build` + `pnpm lint` green when `web/` changed.
- Default request (no anchors/summary, no critic, default tier) renders the same system prompt as
  before this branch (asserted by a test).
- README + AGENTS.md describe the new endpoint, settings, and `evals/`.

## New settings (to add to `.env.example` by the user)

T1 (history compression):

| Setting | Default | Meaning |
|---|---|---|
| `SESSION_MAX_ANCHORS` | `5` | Max turns kept verbatim as commitments per session; the oldest is dropped beyond it (`0` disables anchors). |
| `SESSION_SUMMARY_MAX_CHARS` | `2000` | Hard cap (min 200) on the running summary of folded turns; also stated to the summarizer. |

T3 (Actor-Critic-Boss):

| Setting | Default | Meaning |
|---|---|---|
| `CRITIC_MODEL` | empty | Optional single `<provider>/<model>` for the Critic (e.g. a cheaper one). Empty reuses the `LLM_MODELS` chain. An invalid value is logged and falls back to the main chain. |
| `REVIEW_MAX_ITERATIONS` | `3` | Max actor attempts per `/estimate/reviewed` request (renamed from `BOSS_MAX_ITERATIONS` in T7r) (min 1); worst case 2 x N LLM calls. |

## Progress

_Updated after each task with commit id and checks._

- T1 done (route: delegated writer), commit `8e1b23c`. Window stays pure: `add_turn` returns evicted `TurnPair`s;
  `HistoryCompressor` (`services/history_compression.py`, EN/ES regex) keeps anchors or folds via
  `ConversationSummarizer` (`services/summarizer.py`, prompt `prompts/summary/v1`). Memory renders as
  trailing `history_memory.j2` block (absent when empty; byte-identical test). Detail route exposes
  `anchors_count`/`summary_chars` (+ `types.ts`). Checks: `uv run pytest` green; `pnpm lint`,
  `pnpm build`, `pnpm test:web` green.
- T2 done (route: delegated writer), commit `d94d0c9`. `evals/` (dataset.py pydantic, metrics.py, run.py, 7-case
  golden_dataset.json); the runner builds `EstimationService` with no caches (NoOp), so every case
  hits the model; no new settings. Metrics parse the Markdown total; insufficient-info case expects
  the heading and no total. `pnpm evals` script, README + AGENTS updated. Checks: `uv run pytest`
  green (382); `python -m evals.run --help` makes no API call.
- T3 done (route: delegated writer). `schemas/{critic,acb}.py`, `services/{critic,boss}.py`, prompt
  `prompts/critic/v1` + trailing `estimation/v3/critic_feedback.j2` (rendered only with feedback;
  stateless path only; default prompt verified byte-identical to pre-change). Decisions:
  `needs_iteration` without a critical/major issue and `reject` without issues are coerced to `accept`
  in the schema validator; critic issues containing prompt-injection patterns are dropped; budget
  exhausted returns the last draft with `final_verdict: needs_iteration`; ACB bypasses both caches.
  `POST /estimate/acb`; `types.ts` mirrors `AcbResponse` (no client function / UI). Checks: see commit.
    Commit `576ef5f`.
- T4 done (route: delegated writer), commit `8cfae9b`. `services/audience.py` (pure regex, EN/ES; precedence documented in the
  module: explicit > compliance terms > executive terms > >=2 dev keywords > session team size <=2 > PM
  signals > default) + trailing `estimation/v3/audience.j2` (after `language.j2`; absent for default, byte-identical
  test). Cache decision: the resolved tier is carried on `EstimationRequest.audience` and added to the exact key
  and the semantic bucket only when non-default (existing keys unchanged); no cache bypass. Optional `audience`
  on JSON body + session form (invalid -> 422); responses (`/estimate`, `/estimate/acb`, session turn, stream
  `done`) carry `audience` + `audience_rule`; session detail `last_audience`/`last_audience_rule`; `types.ts`
  mirrored. No new settings. 

- T5 done (route: delegated writer). `estimation-flow` overview gained three nodes (Audience tier, Actor-Critic-Boss
  with its Critic, History compression), 5 edges, 2 cards; the router node now covers `/estimate/acb`. All cited line
  ranges re-verified against HEAD `8cfae9b`; archify `finalize --repo-root .` passed (validate, deliver, check,
  browser-check). Advisory: 3 route crossings near the service node, not visually inspected. Commit `af98b85`.
- T6 done (route: delegated writer). UI is session-only (client.ts has no stateless/stream function), so the
  `audience` form field is sent on session estimates only; selector "Automática/Auto" omits it, not persisted
  (other options do not persist either). Badge `Para: <tier>` on each result with the rule as tooltip; the
  session-memory block in the sidebar (anchors, summary chars when >0, last audience) refreshes after each turn via a
  best-effort `getSession` (no polling). Rebuilt threads show the badge only on the last turn. Checks: lint, build,
  `pnpm test:web` (105), `uv run pytest` green. Commit: see git log.
- T7a done (route: delegated writer). `Boss.run(actor, critic)` was already callable-based, so both paths share it:
  `generate_for_session_with_critic` builds a session actor (`_session_messages` with optional `critic_feedback`;
  loader now allows feedback together with metadata/memory) and records the turn via `_record_session_turn`, the same
  code as `generate_for_session`. `SessionAcbResponse`; `TurnRecord.final_verdict` -> `SessionTurnView.final_verdict`
  (+ `types.ts`, types only). Diagram `candidate.json` not changed (ACB node now also serves sessions; text not
  updated). Checks: `uv run pytest` green; lint/build/test:web green. Commit: `f1fdf03`.
- T7r done (route: delegated writer). Pure rename: `boss.py`/`Boss`/`BossResult` -> `review_loop.py`/`ReviewLoop`/`ReviewLoopResult`; `schemas/acb.py` -> `schemas/review.py` (`ReviewIteration`, `ReviewedEstimateResponse`, `SessionReviewedEstimateResponse`); routes `/estimate/reviewed` and `/sessions/{id}/estimate/reviewed` (no aliases); `BOSS_MAX_ITERATIONS` -> `REVIEW_MAX_ITERATIONS`; log events `review_iteration`/`review_budget_exhausted`; tests renamed to `test_critic_review.py`/`test_session_review.py`; `types.ts`, README, AGENTS.md and diagram updated (review node now covers the session route). Checks: pytest, lint, build, test:web green. T7b: use the new names. Commits: see git log.

## Next step

user: review, add new settings to `.env.example`, push/PR.
