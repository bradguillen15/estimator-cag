-- ============================================================
-- Session 8 live, block 2.2
-- Building the full-precision HNSW index (vector_cosine_ops)
-- ============================================================
--
-- This is a TEACHING step: the schema (migration 0003) only owns the halfvec index
-- `chunks_embedding_halfvec_idx`. The full-precision index created here is named
-- `chunks_embedding_idx`; 99_revert_live_session.sql drops it again.
--
-- How to run it: psql lives in the Postgres container, which does NOT mount this file.
-- Two options from the repo root:
--
--   docker compose exec -T estimator-postgres psql -U estimator -d estimator \
--     < scripts/s08/sql/01_create_hnsw.sql
--
-- or open an interactive psql and paste the blocks one by one (recommended live, to
-- comment each step):
--
--   docker compose exec estimator-postgres psql -U estimator -d estimator

-- Check the current state: after `alembic upgrade head` you see the relational indexes
-- (B-tree + GIN) and the halfvec HNSW index, but no full-precision vector index yet.
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'chunks';

-- Build the HNSW index. The three decisions taken here:
--   - m = 16              -> connections per graph node. Reasonable default for 1536
--                            dimensions; raising it improves recall at the cost of
--                            memory and build time.
--   - ef_construction=128 -> candidate list size while building. Raised from pgvector's
--                            default (64): a better graph for a slower build.
--   - vector_cosine_ops   -> COSINE operator class. It must line up with the <=>
--                            operator of the queries; otherwise Postgres ignores the
--                            index SILENTLY (see block 2.3).
CREATE INDEX chunks_embedding_idx
ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 128);

-- Check that the index exists and how big it is.
-- Compare its size with the table's: HNSW is not free.
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'chunks';
