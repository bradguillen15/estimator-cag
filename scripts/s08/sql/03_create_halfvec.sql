-- ============================================================
-- Session 8 live, block 4.1
-- The halfvec index next to the full-precision one
-- ============================================================
--
-- halfvec stores each component in 16 bits (half precision) instead of 32. The embedding
-- column does NOT change (it stays vector(1536), full precision in the table): only the
-- INDEX is built on the cast expression. Result: an index about 50% smaller that, for
-- normalized embeddings such as OpenAI's, returns indistinguishable results.
--
-- Migration 0003 (`alembic upgrade head`) already creates this index as
-- `chunks_embedding_halfvec_idx`, and `PostgresChunkStore.search` queries through it.
-- The CREATE below is IF NOT EXISTS, so it is a no-op on a migrated database and only
-- restores the index if you dropped it by hand during the demo. Do not rename it: the
-- migration owns the name.

-- Size of the current vector index, to have the reference in front of you
-- (needs 01_create_hnsw.sql first).
SELECT pg_size_pretty(pg_relation_size('chunks_embedding_idx')) AS vector_index_size;

-- The halfvec index on the expression (embedding::halfvec(1536)).
-- Mind the two details:
--   - the double parentheses: it is an EXPRESSION index, not a column index.
--   - halfvec_cosine_ops: the operator class must be the halfvec one.
-- And the consequence not to forget: this index only serves queries that order by THE
-- SAME cast expression. A query ordering by `embedding <=> ...` (no cast) will not use it.
CREATE INDEX IF NOT EXISTS chunks_embedding_halfvec_idx
ON chunks
USING hnsw ((embedding::halfvec(1536)) halfvec_cosine_ops)
WITH (m = 16, ef_construction = 128);

-- Compare the sizes of both indexes side by side.
-- Expected: halfvec takes about half.
SELECT
    indexrelname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'chunks'
  AND indexrelname LIKE '%embedding%';

-- Quick check that the halfvec index answers: same top-5 query with the cast expression.
-- The plan should show "Index Scan using chunks_embedding_halfvec_idx".
EXPLAIN ANALYZE
SELECT id, chunk_type
FROM chunks
ORDER BY (embedding::halfvec(1536)) <=> (
    SELECT embedding::halfvec(1536) FROM chunks ORDER BY id LIMIT 1
)
LIMIT 5;
