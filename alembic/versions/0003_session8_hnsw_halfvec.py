"""Session 8 live — HNSW index on the halfvec expression of ``chunks.embedding``.

Revision ID: 0003_session8_hnsw_halfvec
Revises: 0002_session8_pgvector
Create Date: 2026-11-01 00:00:00

Migration 0002 shipped no vector index on purpose (the sequential scan was the baseline); this one adds the final
state of the live session. The column stays ``vector(1536)`` (full precision on disk); only the INDEX is built on
the half-precision cast, which is roughly half the size and returns indistinguishable results for normalized
embeddings such as OpenAI's.

Because it is an expression index, Postgres only uses it for queries that order by the exact same expression:
``(embedding::halfvec(1536)) <=> :q``. ``PostgresChunkStore.search`` casts to ``HALFVEC(EMBEDDING_DIMENSIONS)``
for that reason; a plain ``embedding <=> :q`` silently falls back to a sequential scan.

The full-precision ``vector_cosine_ops`` HNSW (``chunks_embedding_idx``) is only a teaching step of the live
session (``scripts/s08/sql/01_create_hnsw.sql``) and is deliberately not part of the schema.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.persistence.models import EMBEDDING_DIMENSIONS

revision: str = "0003_session8_hnsw_halfvec"
down_revision: Union[str, None] = "0002_session8_pgvector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "chunks_embedding_halfvec_idx"


def upgrade() -> None:
    # m / ef_construction: m=16 is the usual default for 1536 dimensions; ef_construction=128 doubles pgvector's
    # default (64) for a better graph at the cost of a slower build.
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON chunks "
        f"USING hnsw ((embedding::halfvec({EMBEDDING_DIMENSIONS})) halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
