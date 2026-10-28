"""Ingest use case: duplicate check -> chunk -> embed -> persist.

Two short transactions, none open during the embeddings call (which may sleep through rate-limit retries):
a read-only duplicate check, then the insert of the document and all its chunks, which commit together. The
document row is only written after the embeddings come back, so a failing embeddings API (or database) leaves no
orphan ``documents`` row. The check is only a fast path: the unique index on ``source_path`` is what rejects a
concurrent identical ingest, surfaced as the same :class:`DuplicateDocumentError`.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder, estimated_cost_usd
from app.embedding_pipeline.schemas import Budget, IngestResponse
from app.embedding_pipeline.store import ChunkStore, DuplicateDocumentError
log = structlog.get_logger()


class EmbeddingIngestService:
    """Persists one budget as a document plus its embedded chunks."""

    def __init__(self, chunker: JSONStructuralChunker, embedder: OpenAIEmbedder, store: ChunkStore) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._store = store

    async def ingest(self, *, source_path: str, document_type: str, budget: Budget) -> IngestResponse:
        started = time.perf_counter()
        async with self._store.transaction() as tx:
            existing_id = await tx.find_document_id(source_path)
        if existing_id is not None:
            raise DuplicateDocumentError(existing_id)

        chunks = self._chunker.chunk([budget])
        # The OpenAI client is sync: run it in a thread so the event loop keeps serving requests.
        # One embeddings.create per batch of up to 100 chunks, never one call per chunk.
        embedded = await asyncio.to_thread(self._embedder.embed_many, chunks)

        async with self._store.transaction() as tx:
            document_id = await tx.add_document_with_chunks(
                source_path=source_path,
                document_type=document_type,
                metadata={
                    "budget_id": budget.budget_id,
                    "client_sector": budget.client_metadata.sector,
                    "main_technology": budget.main_technology,
                    "year": budget.year,
                },
                chunks=embedded,
            )

        response = IngestResponse(
            document_id=document_id,
            chunks_created=len(embedded),
            embedding_dimension=len(embedded[0].embedding) if embedded else 0,
            ingestion_time_ms=int((time.perf_counter() - started) * 1000),
        )
        total_tokens = sum(chunk.token_count for chunk in embedded)
        log.info(
            "embeddings_ingest_persisted",
            source_path=source_path,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd(total_tokens),
            **response.model_dump(),
        )
        return response
