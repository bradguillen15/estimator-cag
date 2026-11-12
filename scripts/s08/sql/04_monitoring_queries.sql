-- ============================================================
-- Session 8 live, block 5.1
-- Index health monitoring queries
-- ============================================================
--
-- These are the queries you take to production. The first one is THE canonical one: keep
-- it in the README and run it whenever something is "inexplicably slow".

-- Canonical query: state of every index on chunks.
--   - idx_scan      -> how many times the index has been used.
--   - last_idx_scan -> when it was last used (Postgres 16+).
--   - size          -> how much space it takes.
SELECT
    indexrelname AS index_name,
    idx_scan AS scans,
    last_idx_scan AS last_used,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'chunks'
ORDER BY idx_scan DESC;

-- Table activity statistics: live vs dead rows and when the statistics were last
-- recomputed. Many dead rows = time for VACUUM; an old last_analyze after a big load =
-- time for ANALYZE.
SELECT
    relname,
    n_live_tup AS live_rows,
    n_dead_tup AS dead_rows,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'chunks';

-- If a vector index has idx_scan = 0 after serving semantic queries, it is almost surely
-- the operator / operator class antipattern from block 2.3 (or, for the halfvec index, a
-- query that dropped the ::halfvec(1536) cast). To check the operator class of each
-- vector index:
SELECT
    i.indexrelname,
    op.opcname AS operator_class
FROM pg_stat_user_indexes i
JOIN pg_index pgi ON pgi.indexrelid = i.indexrelid
JOIN pg_opclass op ON op.oid = ANY (pgi.indclass::oid[])
WHERE i.relname = 'chunks'
  AND (op.opcname LIKE 'vector%' OR op.opcname LIKE 'halfvec%');

-- Complements outside psql (mentioned, not demonstrated):
--   - pg_stat_statements -> ranking of queries by cumulative time.
--   - The service's structured logs (structlog): the `semantic_search_done` event carries
--     search_time_ms, useful to correlate end-to-end latency spikes with the plans here.
