# Session 8 live: HNSW + halfvec port

## Objective
Port the session 8 live material from the course repo (`ai-engineering`, branch `session_08_live`) into
estimator-cag, adapted to this repo's layout, on branch `session_08`.

## Problem / why
`/search` does a sequential scan (migration `0002` ships no vector index on purpose: it was the baseline).
The live session adds an HNSW index on a `halfvec` expression, Postgres tuning for index builds, and
measurement / monitoring / maintenance scripts. None of it is here yet.

## Scope
- Alembic migration `0003`: HNSW index on `(embedding::halfvec(1536)) halfvec_cosine_ops`, `m=16`,
  `ef_construction=128` (final state of the live session; the full-precision vector HNSW is only a teaching step).
- `PostgresChunkStore.search` orders by the same casted expression, or the index is silently ignored.
- `docker-compose.yml` `estimator-postgres`: `shm_size` + build-tuning `-c` flags.
- Scripts under `scripts/s08/` (Python + `sql/`), comments and output in English, using `app.config` settings.
- Tests, README, AGENTS.md (§1, §3, §7 statements about "no vector index").

## Constraints
- AGENTS.md layer rules: sqlalchemy/pgvector imports only under `app/persistence/` (scripts may import `app.*`).
- English for every developer-facing artifact.
- No commits unless the user asks (user memory rule).
- TDD: not configured (unknown). Ordinary functional checks: `pnpm test:api`.

## Tasks
- [x] T1 Migration `0003` with the halfvec HNSW expression index (downgrade drops it). Route: delegated writer.
- [x] T2 Search query casts to `HALFVEC(EMBEDDING_DIMENSIONS)`; regression test asserting the compiled SQL uses
      the cast. Route: delegated writer.
- [x] T3 docker-compose Postgres tuning. Route: delegated writer.
- [x] T4 Port measurement, monitoring, maintenance and revert scripts to `scripts/s08/`. Route: delegated writer.
- [x] T5 Docs: README, AGENTS.md. Route: delegated writer.

Route evidence: 2+ non-trivial files → writer trigger → one delegated writer.

## Acceptance criteria
- `pnpm test:api` passes.
- `alembic upgrade head` creates `chunks_embedding_halfvec_idx`; `EXPLAIN` of the search query uses it.
- Docs no longer claim there is no vector index.

## Checks
- `pnpm test:api` (required). Live Postgres migration: manual (not in CI, AGENTS.md §7 #10).

## Progress
- T1-T5 written by one delegated writer (not committed). Evidence: `uv run pytest -q` all pass (new regression test
  `test_search_statement_orders_by_the_halfvec_cast_the_hnsw_index_is_built_on` in tests/test_persistence.py);
  AST parse of `scripts/s08/*.py` + migration 0003 OK; `docker compose config -q` OK; s08 modules import cleanly.
- Live Postgres (2026-11-01): container recreated with the tuning (`maintenance_work_mem` 512MB, ShmSize 1GiB);
  `uv run alembic upgrade head` → `0003_session8_hnsw_halfvec`, `chunks_embedding_halfvec_idx` exists (248 kB, 60 rows).
  The app's compiled ORDER BY is `CAST(chunks.embedding AS HALFVEC(1536)) <=> :q`. EXPLAIN of that expression: seq scan
  + sort at 60 rows (planner's cost choice), `Index Scan using chunks_embedding_halfvec_idx` with `enable_seqscan=off`,
  so the expression matches the index. `PostgresChunkStore.search` with a stored embedding returns itself at distance 0.
- Not verified: the s08 scripts (billed embedding calls), index use at scale without forcing the planner.

## Next step
Commit when asked.

## Follow-ups
- Archify diagram (`docs/architecture/estimation-flow/`) node for the vector store could mention the HNSW index.
