"""Semantic search over the persisted corpus (session 8).

The query is embedded with the SAME model used at ingest time (distances between vectors of different models are
meaningless), then ranked by cosine distance in SQL. No vector index and no metadata filters yet: both are built
in the live session on top of this baseline.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import SearchResponse
from app.embedding_pipeline.store import ChunkStore

log = structlog.get_logger()


class SemanticRetriever:
    def __init__(self, embedder: OpenAIEmbedder, store: ChunkStore) -> None:
        self._embedder = embedder
        self._store = store

    async def search(self, *, query: str, k: int) -> SearchResponse:
        started = time.perf_counter()
        # Sync OpenAI client -> thread, as in the ingest path.
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query)
        hits = await self._store.search(query_vector, k)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # The query text is not logged: users may paste emails or secrets into it.
        log.info("semantic_search_done", k=k, results=len(hits), search_time_ms=elapsed_ms)
        return SearchResponse(query=query, k=k, search_time_ms=elapsed_ms, results=hits)
