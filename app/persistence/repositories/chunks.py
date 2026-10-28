"""Postgres + pgvector ``ChunkStore`` (async, asyncpg). Callers see Protocols and schemas, never ORM rows."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.embedding_pipeline.schemas import EmbeddedChunk, SearchHit
from app.embedding_pipeline.store import BUDGET_COMPONENT
from app.persistence.models import ChunkRow, DocumentRow


class SqlChunkStoreTransaction:
    """Works on a session whose transaction is owned by :meth:`PostgresChunkStore.transaction`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_document_id(self, source_path: str) -> int | None:
        stmt = select(DocumentRow.id).where(DocumentRow.source_path == source_path).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add_document_with_chunks(
        self,
        *,
        source_path: str,
        document_type: str,
        metadata: dict,
        chunks: list[EmbeddedChunk],
    ) -> int:
        document = DocumentRow(source_path=source_path, document_type=document_type, metadata_=metadata)
        self._session.add(document)
        await self._session.flush()  # assigns document.id; nothing is committed yet
        self._session.add_all(
            ChunkRow(
                document_id=document.id,
                chunk_type=BUDGET_COMPONENT,
                content=chunk.text,
                embedding=chunk.embedding,
                metadata_={"chunk_id": chunk.chunk_id, "token_count": chunk.token_count, **chunk.metadata},
            )
            for chunk in chunks
        )
        return document.id


class PostgresChunkStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlChunkStoreTransaction]:
        """One session, one transaction: commit when the block exits, roll back if it raises."""
        async with self._session_factory() as session, session.begin():
            yield SqlChunkStoreTransaction(session)

    async def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        """k-NN by cosine distance (pgvector ``<=>``). No vector index yet, so this is a sequential scan.

        Cosine rather than L2 or inner product: OpenAI embeddings are normalized, so the ranking would match, but
        cosine is the RAG convention and lines up with the ``vector_cosine_ops`` operator class of a future HNSW
        index (an operator that does not match the index's operator class makes Postgres silently skip it).
        """
        distance = ChunkRow.embedding.cosine_distance(query_vector)
        stmt = (
            select(
                ChunkRow.id,
                ChunkRow.document_id,
                ChunkRow.chunk_type,
                ChunkRow.content,
                ChunkRow.metadata_,
                distance.label("distance"),
            )
            .where(ChunkRow.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_type=row.chunk_type,
                content=row.content,
                distance=float(row.distance),
                metadata=row.metadata_,
            )
            for row in rows
        ]
