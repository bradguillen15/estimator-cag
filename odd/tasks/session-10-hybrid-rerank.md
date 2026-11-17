# Session 10 pre-work: hybrid search + cross-encoder reranking

## Objective

Add a lexical (Postgres full-text) branch fused with the existing vector search via Reciprocal Rank Fusion, plug in a
cross-encoder reranker (recall top-50, keep top-5), and measure four configurations (A vector, B hybrid, C vector +
rerank, D hybrid + rerank) on a hand-labelled golden set: precision@5 and latency.

## Problem / why

"Similar" is not "relevant": cosine k-NN can surface a payments budget for an e-commerce query. Hybrid search and
reranking should help, but the point is to prove by how much and at what latency cost.

## Scope

- Alembic migration 0004: generated `tsvector` column on `chunks` + GIN index.
- Lexical search in `PostgresChunkStore`; pure RRF function; hybrid retrieval mode.
- Cross-encoder wrapper ported from the official course repo (`LIDR-academy/ai-engineering`, branch `session_10`,
  `estimator/app/generation/rag/retrieval/reranker.py` + `verify_reranker.py`), adapted to this layout. Fusion and
  pipeline are written here, not copied (the official branch ships them solved).
- Search mode and rerank toggle without code changes (request params + settings defaults).
- Golden set (5 queries, hand-labelled relevant budgets) + measurement script + results table + conclusions.

Out of scope: query expansion, multi-index routing, metadata filtering (built in the live session).

## Constraints / decisions

- Corpus (`data/budgets_sample.json`) is **English**, not Spanish as the exercise text assumes -> text search config
  `english`. Golden queries are written in English to match.
- Layout follows `app/embedding_pipeline/` (course reference layout, AGENTS.md §7 #12); SQLAlchemy only in
  `app/persistence/`; `sentence_transformers` imported lazily inside the reranker only.
- Tests never load torch or touch Postgres: fake reranker / fake store.
- TDD: off (project default, source: prior ODD docs). Runner: `uv run pytest` (`pnpm test:api`).

## Tasks

- [x] T1 Migration 0004 tsvector + GIN; model column; lexical search in store
- [x] T2 RRF fusion + hybrid mode + reranker integration + toggles + unit tests
- [x] T3 Golden set + measurement script; run A/B/C/D against live Postgres
- [ ] T4 Results table + conclusions doc; README/AGENTS updates; PR (docs done; `.env.example` mirror and PR pending)

Route: T1+T2 delegated direct (writer trigger: 2+ non-trivial files). T3 run inline (measurement). T4 inline docs.

## Acceptance criteria

- `uv run alembic upgrade head` applies 0004; GIN index used by the lexical query.
- All four configurations invocable reproducibly from one script.
- `pnpm test:api` green.
- Table with precision@5 and latency per configuration.

## Progress

- Branch `session-10/pre-work` created from `main`.
- Golden labels reviewed against every component: q2 -> only BUD-2024-001, q3 -> only BUD-2024-009.
- Evidence: `uv run pytest` 601 passed; `alembic upgrade head` applied 0004 on local Postgres (60 chunks, 60 tsv);
  `verify_reranker` OK; eval run (10 repeats): A 0.80/4.0 ms, B 0.80/5.1 ms, C 0.88/653 ms, D 0.88/665 ms
  (chunk P@5 / median latency). Report: `evals/retrieval/REPORT.md`.
- Known: `import app.main` loads torch already on baseline (spaCy/presidio chain), not caused by this work.
- Pending: `.env.example` mirror of the 6 new settings (writer edit was denied; user to apply); no commits yet
  (user rule: commit only when asked); Engram mirror pending (save blocked by auto-mode hook check).
