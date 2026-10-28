"""Vector store abstraction for the embedding pipeline (session 8).

The ingest service sees these Protocols only; the Postgres + pgvector implementation lives in
``app/persistence/repositories/chunks.py``, the only place that touches SQLAlchemy.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from app.embedding_pipeline.schemas import EmbeddedChunk, SearchHit

# The structural chunker emits one chunk per budget component.
BUDGET_COMPONENT = "budget_component"


class ChunkStoreTransaction(Protocol):
    """Operations that run inside one database transaction (committed on exit, rolled back on error)."""

    async def find_document_id(self, source_path: str) -> int | None: ...

    async def add_document_with_chunks(
        self,
        *,
        source_path: str,
        document_type: str,
        metadata: dict,
        chunks: list[EmbeddedChunk],
    ) -> int: ...


class ChunkStore(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChunkStoreTransaction]: ...

    async def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        """The ``k`` chunks nearest to ``query_vector`` by cosine distance, closest first."""
        ...
