"""In-memory ``ChunkStore`` with real transaction semantics: writes land only if the block exits cleanly."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.embedding_pipeline.schemas import EmbeddedChunk, SearchHit
from app.embedding_pipeline.store import BUDGET_COMPONENT


@dataclass
class StoredDocument:
    id: int
    source_path: str
    document_type: str
    metadata: dict
    chunks: list[EmbeddedChunk]


@dataclass
class FakeChunkStore:
    documents: list[StoredDocument] = field(default_factory=list)
    rollbacks: int = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_FakeTransaction]:
        tx = _FakeTransaction(self)
        try:
            yield tx
        except BaseException:
            self.rollbacks += 1
            raise
        self.documents.extend(tx.pending)

    async def search(self, query_vector: list[float], k: int) -> list[SearchHit]:
        hits = [
            SearchHit(
                chunk_id=document.id * 1000 + index,
                document_id=document.id,
                chunk_type=BUDGET_COMPONENT,
                content=chunk.text,
                distance=_cosine_distance(query_vector, chunk.embedding),
                metadata=chunk.metadata,
            )
            for document in self.documents
            for index, chunk in enumerate(document.chunks)
        ]
        return sorted(hits, key=lambda hit: hit.distance)[:k]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return 1 - dot / (math.hypot(*a) * math.hypot(*b))


class _FakeTransaction:
    def __init__(self, store: FakeChunkStore) -> None:
        self._store = store
        self.pending: list[StoredDocument] = []

    async def find_document_id(self, source_path: str) -> int | None:
        return next((d.id for d in self._store.documents if d.source_path == source_path), None)

    async def add_document_with_chunks(
        self, *, source_path: str, document_type: str, metadata: dict, chunks: list[EmbeddedChunk]
    ) -> int:
        document = StoredDocument(
            id=len(self._store.documents) + len(self.pending) + 1,
            source_path=source_path,
            document_type=document_type,
            metadata=metadata,
            chunks=chunks,
        )
        self.pending.append(document)
        return document.id
