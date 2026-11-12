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


class DuplicateDocumentError(Exception):
    """A document with the same ``source_path`` is already ingested."""

    def __init__(self, document_id: int) -> None:
        super().__init__(f"Document already ingested (id={document_id})")
        self.document_id = document_id


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
    ) -> int:
        """Insert the document and its chunks. Raises :class:`DuplicateDocumentError` when ``source_path`` is
        already taken (the unique index decides, so concurrent ingests cannot both win)."""
        ...


class ChunkStore(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChunkStoreTransaction]: ...

    async def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        """The ``k`` chunks nearest to ``query_vector`` by cosine distance, closest first."""
        ...
