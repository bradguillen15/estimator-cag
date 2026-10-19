# Session 06 live: CAG stress-test scaffolding + data ingestion

## Objective

Port the additions of the reference course branch `ai-engineering` `origin/session_06_live`
(estimator/) into estimator-cag, adapted to this codebase's layers (AGENTS.md), on branch
`session_6_live`. Plan: `~/.claude/plans/segun-estas-indicaciones-hay-agile-minsky.md`.

## Why

Session 6 adds (a) per-turn telemetry and a stress harness that measures where CAG degrades, and
(b) the data-driven ingestion foundation (catalog, parsers, cleaning, PII pseudonymization,
Postgres) that session 7 RAG builds on. estimator-cag has none of it.

## Scope

- In: `TurnObservation` + `turn_observed`, `evals/stress/` (scaffolding + REPORT.md template),
  `app/services/ingestion/` (catalog, loader, documents, parsers, cleaning, PII, orchestrator,
  architecture helper), `app/persistence/` (SQLAlchemy, Alembic, Postgres pgvector image), ingestion
  API, seed data, demo/preflight scripts, docs.
- Out: running the billed stress test / filling REPORT.md numbers (user decision), Rails client,
  `unstructured[all-docs]`, XLSX parser / openpyxl, vector columns (session 7).

## Constraints

- AGENTS.md layer rules: no FastAPI in services; `sqlalchemy`/`psycopg` only under `app/persistence/`;
  env reads only in `config.py`; collaborators injected via `dependencies.py`; no import-time engine.
- Tests never reach a real LLM, Postgres or spaCy model (fakes / stubs only).
- `.env.example` is not readable/writable by the agent: new settings are listed for the user.
- Commits only with explicit user OK (memory rule); Conventional Commits, no AI attribution,
  Node 24 first in PATH (`~/.nvm/versions/node/v24.21.0/bin`) for the Husky hook. Never `--no-verify`.

## Workflow settings

- TDD: off (no project/session TDD config; source: none). Ordinary functional checks per task.
- Runner: `uv run pytest` (API); `pnpm test:web` + `pnpm lint` + `pnpm build` when `web/` changes.
- RDD: off (global, per previous session doc).
- Delivery: ask-on-risk; forecast well over 400 authored lines (~4-5k) across 7 work units on one
  branch. Push/PR and chaining strategy are the user's decision.

## Tasks

- [x] T1 — Turn observation. Route: delegated writer (multi-file). `UsageTotals` accumulator +
  optional `metrics=` on `complete`/`complete_messages`; tokens/cost sum every completed call of the
  turn (actor attempts, critic, extractor, summarizer); `latency_ms` = wall clock of the whole turn;
  `turn_index` = uncapped `Session.turn_count`; `cache_hit_kind` always "none". `observation` on both
  session routes; `SessionDetail` adds `summary`, `anchors`, `last_observation`; types.ts mirrored.
  Checks: `uv run pytest -q` all pass; `pnpm lint` clean; `tsc -b --noEmit` clean; `pnpm test:web`
  117 passed. Commit: pending user OK.
- [ ] T2 — Stress harness, no run. Route: delegated writer.
- [ ] T3 — Catalog, documents, loader, parsers, seed data. Route: delegated writer.
- [ ] T4 — Cleaning + PII pseudonymization. Route: delegated writer.
- [ ] T5 — Postgres persistence (SQLAlchemy, Alembic, compose, settings). Route: delegated writer.
  `scripts/dev.mjs` (user request): always start `estimator-postgres` (`docker compose up -d --wait`),
  then `uv run alembic upgrade head` before the API; on Ctrl+C/exit `docker compose stop` it only if
  started here (same pattern as Redis; data kept in the volume). Docker missing → warn, keep going.
- [ ] T6 — Ingestion API + DI + lifespan catalog log. Route: delegated writer.
- [ ] T7 — Architecture helper, preflight, docs (AGENTS.md, README). Route: delegated writer.

## Progress

- Branch `session_6_live` created off `session_5_live` (77058f3).

## Next step

T1.
