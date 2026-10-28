"""SQLAlchemy models: the pseudonym mapping table, the ingestion job tracker and the vector store.

``pseudonym_mappings`` is keyed by ``(entity_type, original_hash)``; the hash is
an HMAC of the original value, so the database alone cannot reveal it.
``ingestion_jobs`` backs the asynchronous ingestion endpoint.
``documents`` / ``chunks`` (session 8) hold the embedded historical budgets: one document, N chunks.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

# Dimensionality of text-embedding-3-small. Not configuration: changing it means re-embedding the whole corpus.
EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    """Single declarative base; Alembic reads its metadata."""


class PseudonymMappingRow(Base):
    __tablename__ = "pseudonym_mappings"
    __table_args__ = (
        UniqueConstraint("entity_type", "original_hash", name="uq_mappings_entity_hash"),
        Index("idx_mappings_lookup", "entity_type", "original_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    pseudonym: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IngestionJobRow(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("idx_jobs_status", "status"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    documents_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentRow(Base):
    """One ingested source (a historical budget): provenance plus document-level metadata.

    ``metadata`` is reserved on declarative models, so the attribute is ``metadata_`` on the ``metadata`` column.
    """

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_source_path", "source_path", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    chunks: Mapped[list[ChunkRow]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class ChunkRow(Base):
    """One embeddable fragment of a document. ``ON DELETE CASCADE``: deleting a document deletes its chunks.

    ``embedding`` is nullable so a chunk could be stored first and embedded later; session 8 always writes both
    in the same transaction. There is deliberately no vector index yet (sequential-scan baseline).
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_chunk_type", "chunk_type"),
        Index("ix_chunks_metadata_gin", "metadata", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[DocumentRow] = relationship(back_populates="chunks")
