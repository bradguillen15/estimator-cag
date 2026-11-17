"""The lexical SQL is compiled (no database): OR semantics, indexable WHERE on content_tsv, deterministic order."""

from sqlalchemy.dialects import postgresql

from app.persistence.models import ChunkRow
from app.persistence.repositories.chunks import _lexical_statement


def _sql() -> str:
    return str(_lexical_statement("shopping cart", 7).compile(dialect=postgresql.dialect()))


def test_where_uses_the_tsv_column_with_or_tsquery() -> None:
    sql = _sql()

    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "chunks.content_tsv @@" in where
    assert "plainto_tsquery('english'::regconfig" in where
    assert "replace(" in where and "TSQUERY" in where.upper()


def test_orders_by_rank_then_id_and_limits() -> None:
    order = _sql().split("ORDER BY", 1)[1]

    assert "ts_rank_cd(chunks.content_tsv" in order and "DESC" in order
    assert "chunks.id" in order and "LIMIT" in order


def test_generated_column_is_computed_so_the_orm_never_writes_it() -> None:
    column = ChunkRow.__table__.c.content_tsv

    assert column.computed is not None and column.computed.persisted
    assert "to_tsvector('english', content)" in str(column.computed.sqltext)
