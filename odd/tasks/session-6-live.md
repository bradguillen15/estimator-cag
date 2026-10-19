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
- Commits: user authorized (2026-10-18) one commit per task on completion without asking; Conventional Commits, no AI attribution,
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
  117 passed.
  Commit: 9d3b78c.
- [x] T2 — Stress harness, no run. Route: delegated writer. `evals/stress/` (scenarios 3×20 turns,
  metrics reusing `MetricResult`, runner `--http` httpx / in-process TestClient with injectable client,
  non-2xx turns recorded as rows with `status_code`/`error`), deterministic `build_pdfs` (fpdf2 dev
  dep; 5455/20732/51286/102573 chars), REPORT.md template (100 KB = HTTP 400, not truncation; budget
  facts only in summary/anchors; caches unused). Checks: 14 new tests, full `uv run pytest -q` green,
  `--help` of runner and build_pdfs OK. No billed run (user decision).
- [x] T3 — Catalog, documents, loader, parsers, seed data. Route: delegated writer. `app/services/ingestion/` (catalog models/loader/inspect, documents.py, loaders.py, parsers json+txt + registry), `data/catalog/catalog.yaml`, `data/seed/`, pyyaml. Checks: full `uv run pytest -q` green; catalog loader CLI → 3 sources, 1 included; inspect CLI lists seeds; no fastapi/sqlalchemy/env reads under ingestion.
- [x] T4 — Cleaning + PII pseudonymization. Route: delegated writer. pandas 3.0.6, pandera 0.34.1, presidio 2.2.364, spacy 3.8.16, faker 40.43 (all OK on 3.13). `cleaning/` (clean, pandera schema, policy) and `pii/` (analyzer by injected model name, recognizers, seeded pseudonymizer, MappingStore Protocol + in-memory). Demos in `scripts/ingestion/`. Checks: full pytest green; demo_cleaning 6 in / 5 dedup / 1 discarded (+3 valid, 1 quarantined); demo_pii 20 mappings. Notes: Presidio auto-downloaded `es_core_news_md` into the local venv on first demo run (not a declared dep; `uv sync` may remove it). Reference quirks kept: BUDGET-2024-0002 quarantined for int vs float dtype, strict schema flags the added `content_hash` column, pandas dayfirst warning.
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
