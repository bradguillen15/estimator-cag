"""Session 8 schema contract: the ORM models match the migration (no live database needed)."""

from pgvector.sqlalchemy import Vector

from app.persistence.models import EMBEDDING_DIMENSIONS, ChunkRow, DocumentRow


def test_chunk_embedding_is_a_nullable_1536_vector() -> None:
    column = ChunkRow.__table__.c.embedding
    assert isinstance(column.type, Vector)
    assert column.type.dim == EMBEDDING_DIMENSIONS == 1536
    assert column.nullable


def test_chunks_cascade_when_their_document_is_deleted() -> None:
    (foreign_key,) = ChunkRow.__table__.c.document_id.foreign_keys
    assert foreign_key.column.table is DocumentRow.__table__
    assert foreign_key.ondelete == "CASCADE"


def test_metadata_is_stored_in_a_column_named_metadata() -> None:
    assert "metadata" in DocumentRow.__table__.c
    assert "metadata" in ChunkRow.__table__.c


def test_source_path_is_unique() -> None:
    (index,) = DocumentRow.__table__.indexes
    assert index.name == "ix_documents_source_path"
    assert index.unique


def test_relational_indexes_exist_but_no_vector_index() -> None:
    indexes = {index.name: index for index in ChunkRow.__table__.indexes}
    assert set(indexes) == {"ix_chunks_document_id", "ix_chunks_chunk_type", "ix_chunks_metadata_gin"}
    assert indexes["ix_chunks_metadata_gin"].dialect_options["postgresql"]["using"] == "gin"
    assert all("embedding" not in index.columns for index in indexes.values())
