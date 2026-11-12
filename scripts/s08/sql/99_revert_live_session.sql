-- ============================================================
-- Session 8 live: revert after a rehearsal (test run -> pre-session state)
-- ============================================================
--
-- Returns the database to the PRE-FLIGHT-COMPLETE state (the starting point of the live
-- session): 30,000 synthetic chunks + the real ones loaded, with ONLY the schema's own
-- halfvec index (`chunks_embedding_halfvec_idx`, owned by migration 0003) and no
-- persistent overrides. It does NOT re-embed anything: it keeps the 30k pre-flight rows
-- to avoid paying for embeddings again (~$0.03 / ~5-10 min).
--
-- What it reverts (everything the session 8 rehearsal leaves behind):
--   - the teaching full-precision index `chunks_embedding_idx` (01_create_hnsw.sql),
--   - the ~100 extra synthetic chunks inserted in block 5.2,
--   - the global ef_search override if it was set with ALTER DATABASE (block 3.1),
--   - the pg_stat counters (idx_scan, last_analyze) for a clean "before".
--
-- What it does NOT touch:
--   - `chunks_embedding_halfvec_idx`: it belongs to Alembic migration 0003, so it is kept
--     on purpose (the application's /search depends on it). If you dropped it by hand,
--     `alembic upgrade head` is NOT enough (the revision is already applied); re-run
--     the IF NOT EXISTS CREATE in 03_create_halfvec.sql instead.
--   - the 30,000 pre-flight synthetic chunks, nor the real ones,
--   - the synthetic document that groups them, any repo file or migration.
--
-- Want a no-index sequential-scan baseline? Do not drop the migration's index here; use
-- `SET enable_indexscan = off;` in your psql session (or `SET LOCAL` in a transaction).
--
-- How to run it (from the repo root, AT THE END of the test run):
--
--   docker compose exec -T estimator-postgres psql -U estimator -d estimator \
--     < scripts/s08/sql/99_revert_live_session.sql
--
-- How many synthetic rows to keep: 30000 by default (what the pre-flight inserts). If you
-- loaded a different amount in the pre-flight, pass it:
--   ... psql ... -v keep_synthetic=50000 < scripts/s08/sql/99_revert_live_session.sql
--
-- Idempotent and fail-safe: if the teaching index is absent nothing is dropped; if there
-- are <= keep_synthetic synthetic rows, no chunk is deleted. Safe to run several times.

\if :{?keep_synthetic}
\else
  \set keep_synthetic 30000
\endif

\echo '== State BEFORE reverting =='
SELECT
    (SELECT count(*) FROM chunks)                              AS total_chunks,
    (SELECT count(*) FROM chunks WHERE chunk_type='synthetic') AS synthetic_chunks;
SELECT indexrelname FROM pg_stat_user_indexes WHERE relname='chunks' ORDER BY indexrelname;

-- 1. Delete the synthetic chunks inserted DURING the session (block 5.2), keeping the
--    :keep_synthetic oldest ones (the pre-flight rows). They are told apart by id
--    (autoincrement): pre-flight rows have the lowest ids; any later synthetic row belongs
--    to the rehearsal. If there are <= keep_synthetic synthetic rows, the subquery returns
--    NULL and nothing is deleted (fail-safe).
DELETE FROM chunks
WHERE chunk_type = 'synthetic'
  AND id > (
      SELECT id
      FROM chunks
      WHERE chunk_type = 'synthetic'
      ORDER BY id
      OFFSET (:keep_synthetic - 1)
      LIMIT 1
  );

-- 2. Drop the teaching full-precision index (idempotent). Also covers an index left
--    INVALID by an aborted CONCURRENTLY build. `chunks_embedding_halfvec_idx` is NOT
--    dropped here: the migration owns it.
DROP INDEX IF EXISTS chunks_embedding_idx;

-- 3. Revert the global ef_search override if it was set with ALTER DATABASE (block 3.1).
--    A session-level SET / SET LOCAL does not persist; this does. Harmless if never set.
ALTER DATABASE estimator RESET hnsw.ef_search;

-- 4. Reset statistics for a pristine "before": idx_scan goes back to 0, so the live
--    antipattern demo (idx_scan=0 -> index ignored, blocks 2.3/5.1) starts clean. ANALYZE
--    then repopulates the planner statistics.
SELECT pg_stat_reset();
ANALYZE chunks;

\echo '== State AFTER reverting =='
SELECT
    (SELECT count(*) FROM chunks)                              AS total_chunks,
    (SELECT count(*) FROM chunks WHERE chunk_type='synthetic') AS synthetic_chunks,
    (SELECT count(*) FROM documents WHERE document_type='synthetic_test') AS synthetic_docs;
-- Expected: relational indexes (chunks_pkey, ix_chunks_*) plus chunks_embedding_halfvec_idx;
-- NO chunks_embedding_idx.
SELECT indexrelname FROM pg_stat_user_indexes WHERE relname='chunks' ORDER BY indexrelname;
