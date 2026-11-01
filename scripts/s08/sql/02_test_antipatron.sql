-- ============================================================
-- Session 8 live, block 2.3
-- Demo of the operator / operator class antipattern
-- ============================================================
--
-- Requires the full-precision index from 01_create_hnsw.sql.
--
-- The idea: the index is built with vector_cosine_ops (operator <=>). If a query orders
-- by <-> (L2 distance), Postgres CANNOT use the index... and does not tell you. No
-- error, no warning: sequential scan and off it goes. The only defence is EXPLAIN ANALYZE.
--
-- To avoid copy-pasting vectors, the query vector is the embedding of an existing chunk
-- (scalar subquery). The top-1 result will be that same chunk at distance 0.0, a handy
-- sanity check.

-- Case 1: operator ALIGNED with the index (vector_cosine_ops + <=>).
-- Expected in the plan: "Index Scan using chunks_embedding_idx".
EXPLAIN ANALYZE
SELECT id, chunk_type
FROM chunks
ORDER BY embedding <=> (SELECT embedding FROM chunks ORDER BY id LIMIT 1)
LIMIT 5;

-- Case 2: operator MISALIGNED (cosine index, query with the L2 <->).
-- Expected in the plan: "Seq Scan on chunks" + a Sort.
-- Look at the "Execution Time" of both cases: the gap is brutal and there was NO error.
-- This is the silent antipattern.
EXPLAIN ANALYZE
SELECT id, chunk_type
FROM chunks
ORDER BY embedding <-> (SELECT embedding FROM chunks ORDER BY id LIMIT 1)
LIMIT 5;

-- The other way to catch it: usage statistics. idx_scan grows with Case 1 but NOT with
-- Case 2. A vector index with idx_scan = 0 in production is almost always this antipattern.
SELECT indexrelname, idx_scan, last_idx_scan
FROM pg_stat_user_indexes
WHERE relname = 'chunks';

-- Same trap, expression flavour (the one the application hits if the cast is dropped):
-- the halfvec index from migration 0003 is only used when the ORDER BY repeats the
-- (embedding::halfvec(1536)) expression. A bare `embedding <=> ...` ignores it.
-- Compare the plans:
EXPLAIN
SELECT id FROM chunks
ORDER BY (embedding::halfvec(1536)) <=> (SELECT embedding::halfvec(1536) FROM chunks ORDER BY id LIMIT 1)
LIMIT 5;

-- ------------------------------------------------------------
-- Variant with an external vector (the real benchmark query).
-- scripts/s08/measure_baseline_s08.py prints the pgvector literal of the first query at
-- the end; replace <embedding_vector> with that literal:
--
-- EXPLAIN ANALYZE
-- SELECT id, chunk_type
-- FROM chunks
-- ORDER BY embedding <=> '<embedding_vector>'::vector
-- LIMIT 5;
-- ------------------------------------------------------------
