"""Session 10 — full-text search: generated ``tsvector`` column + GIN index on ``chunks.content``.

Revision ID: 0004_session10_chunks_tsvector
Revises: 0003_session8_hnsw_halfvec
Create Date: 2026-11-17 00:00:00

Adds the lexical half of hybrid search. ``content_tsv`` is a ``GENERATED ALWAYS ... STORED`` column: Postgres
recomputes it on every INSERT/UPDATE of ``content``, so it can never drift from the text (no trigger, no
application code, and the ORM never writes it). The GIN index makes ``content_tsv @@ query`` an index lookup
instead of a sequential scan.

The text search configuration is ``english`` because the corpus (``data/budgets_sample.json``) is English: it
drives stemming ("payments" -> "payment") and stop-word removal. The exercise text assumes Spanish data; with a
Spanish corpus the configuration would be ``spanish`` (the expression below and the one in
``PostgresChunkStore.search_lexical`` must then change together).

Existing rows are backfilled by Postgres while the column is added (table rewrite), which is instant at this size.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004_session10_chunks_tsvector"
down_revision: Union[str, None] = "0003_session8_hnsw_halfvec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "chunks_content_tsv_idx"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute(f"CREATE INDEX {INDEX_NAME} ON chunks USING gin (content_tsv)")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
