-- ============================================================
-- Session 8 live, block 5.2
-- Maintenance cycle: ANALYZE, VACUUM, REINDEX CONCURRENTLY
-- ============================================================
--
-- Live context: we just inserted ~100 synthetic chunks with
-- scripts/s08/insert_synthetic_chunks_s08.py to simulate corpus growth. Now comes the
-- cycle that keeps the vector database healthy in production.
--
-- NOTE: REINDEX ... CONCURRENTLY and VACUUM cannot run inside a transaction. Interactive
-- psql (autocommit) is fine; if you pipe the whole file, psql runs it statement by
-- statement and it also works.

-- Previous state: live/dead rows and when the statistics were updated.
-- After the synthetic insert, last_analyze will be stale.
SELECT n_live_tup, n_dead_tup, last_analyze, last_vacuum
FROM pg_stat_user_tables
WHERE relname = 'chunks';

-- Step 1 - ANALYZE: recompute the statistics the planner uses.
-- Fast and non-blocking. After a big load, ALWAYS.
ANALYZE chunks;

-- Check that last_analyze just changed:
SELECT n_live_tup, n_dead_tup, last_analyze
FROM pg_stat_user_tables
WHERE relname = 'chunks';

-- Step 2 - VACUUM ANALYZE: besides statistics, reclaims the space of dead rows
-- (updates/deletes). This table is almost all inserts, so there is little to reclaim;
-- the point is the habit.
VACUUM ANALYZE chunks;

-- Step 3 - REINDEX CONCURRENTLY: rebuilds the HNSW index without blocking queries.
-- Underneath: it builds a new parallel index, waits until it is ready and swaps it
-- atomically with the old one. It costs double the temporary space and more time than a
-- plain REINDEX, but the service does not notice. In production: low-traffic window.
REINDEX INDEX CONCURRENTLY chunks_embedding_halfvec_idx;

-- Check that the index is still active and operational after the swap.
-- (In Postgres 16, REINDEX CONCURRENTLY keeps the usage statistics: idx_scan is NOT
-- reset, the counter follows the new index.)
SELECT
    indexrelname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size,
    idx_scan
FROM pg_stat_user_indexes
WHERE relname = 'chunks';

-- Indicative production cadences:
--   - ANALYZE -> triggered by autovacuum on its own; manual after bulk loads.
--   - VACUUM  -> weekly (or a well-configured autovacuum).
--   - REINDEX -> monthly, or on observed recall/latency degradation (the HNSW graph
--                degrades with many updates/deletes).
