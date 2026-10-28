"""In-memory ``ChunkStore`` with real transaction semantics: writes land only if the block exits cleanly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.embedding_pipeline.schemas import EmbeddedChunk


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
