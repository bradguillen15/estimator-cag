"""Search over the persisted corpus (sessions 8 and 10).

The query is embedded with the SAME model used at ingest time (distances between vectors of different models are
meaningless). Retrieval then runs in one of four configurations, chosen per request (or from settings):

* **vector** (A): cosine k-NN, ``k`` hits. Unchanged session 8 behaviour.
* **hybrid** (B): vector top ``recall_k`` + Postgres full-text top ``recall_k``, fused with Reciprocal Rank Fusion,
  best ``k`` kept.
* **vector + rerank** (C) / **hybrid + rerank** (D): the candidate set above is recalled wide (``recall_k``),
  rescored by a cross-encoder and cut to ``rerank_top_n``.

Final count rule: when reranking is on, the response holds ``rerank_top_n`` hits (the point of reranking is the cut
after recall), whatever ``k`` the request carried; ``k`` only sizes the recall when reranking is off.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import structlog

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.fusion import reciprocal_rank_fusion
from app.embedding_pipeline.reranker import Reranker
from app.embedding_pipeline.schemas import SearchHit, SearchResponse
from app.embedding_pipeline.store import ChunkStore

log = structlog.get_logger()

SearchMode = Literal["vector", "hybrid"]


class RerankerUnavailableError(RuntimeError):
    """Reranking was requested but no reranker is configured."""


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class SemanticRetriever:
    def __init__(
        self,
        embedder: OpenAIEmbedder,
        store: ChunkStore,
        *,
        reranker: Reranker | None = None,
        default_mode: SearchMode = "vector",
        default_rerank: bool = False,
        recall_k: int = 50,
        rerank_top_n: int = 5,
        rrf_k: int = 60,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._default_mode = default_mode
        self._default_rerank = default_rerank
        self._recall_k = recall_k
        self._rerank_top_n = rerank_top_n
        self._rrf_k = rrf_k

    async def search(
        self, *, query: str, k: int, mode: SearchMode | None = None, rerank: bool | None = None
    ) -> SearchResponse:
        """Embed the query once, then run the configured retrieval. ``None`` = the settings default."""
        started = time.perf_counter()
        # Sync OpenAI client -> thread, as in the ingest path.
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query)
        embed_ms = _ms(started)
        return await self.search_with_vector(
            query=query, query_vector=query_vector, k=k, mode=mode, rerank=rerank, embed_ms=embed_ms
        )

    async def search_with_vector(
        self,
        *,
        query: str,
        query_vector: list[float],
        k: int,
        mode: SearchMode | None = None,
        rerank: bool | None = None,
        embed_ms: int = 0,
    ) -> SearchResponse:
        """Retrieval with a precomputed query vector (no embeddings call).

        Lets a measurement script embed each query once and time only the retrieval side per configuration.
        """
        started = time.perf_counter() - embed_ms / 1000  # so search_time_ms includes the embedding
        effective_mode = mode or self._default_mode
        effective_rerank = self._default_rerank if rerank is None else rerank
        if effective_rerank and self._reranker is None:
            raise RerankerUnavailableError("Reranking was requested but no reranker is configured.")

        retrieval_started = time.perf_counter()
        vector_count, lexical_count, candidates = await self._recall(
            query, query_vector, k, effective_mode, effective_rerank
        )
        retrieval_ms = _ms(retrieval_started)

        rerank_ms = 0
        if effective_rerank:
            rerank_started = time.perf_counter()
            results = await self._rerank(query, candidates)
            rerank_ms = _ms(rerank_started)
        else:
            results = candidates[:k]

        search_time_ms = _ms(started)
        # The query text is not logged: users may paste emails or secrets into it.
        log.info(
            "search_done",
            mode=effective_mode,
            rerank=effective_rerank,
            k=k,
            vector_hits=vector_count,
            lexical_hits=lexical_count,
            candidates=len(candidates),
            results=len(results),
            embed_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            search_time_ms=search_time_ms,
        )
        return SearchResponse(
            query=query,
            k=k,
            mode=effective_mode,
            rerank=effective_rerank,
            search_time_ms=search_time_ms,
            embed_ms=embed_ms,
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            results=results,
        )

    async def _recall(
        self, query: str, query_vector: list[float], k: int, mode: SearchMode, rerank: bool
    ) -> tuple[int, int, list[SearchHit]]:
        """Candidate hits in final-ranking order, plus the hit count of each branch (lexical 0 in vector mode)."""
        if mode == "vector":
            hits = await self._store.search(query_vector, self._recall_k if rerank else k)
            return len(hits), 0, hits

        vector_hits, lexical_hits = await asyncio.gather(
            self._store.search(query_vector, self._recall_k),
            self._store.search_lexical(query, self._recall_k),
        )
        by_id = {hit.chunk_id: hit for hit in lexical_hits}
        by_id.update({hit.chunk_id: hit for hit in vector_hits})  # vector hit wins: it carries the distance
        fused = reciprocal_rank_fusion(
            [[hit.chunk_id for hit in vector_hits], [hit.chunk_id for hit in lexical_hits]], k=self._rrf_k
        )
        candidates = [by_id[chunk_id].model_copy(update={"rrf_score": score}) for chunk_id, score in fused]
        return len(vector_hits), len(lexical_hits), candidates

    async def _rerank(self, query: str, candidates: list[SearchHit]) -> list[SearchHit]:
        """Rescore with the cross-encoder (CPU-bound, sync -> thread) and keep ``rerank_top_n``."""
        assert self._reranker is not None  # checked by the caller
        if not candidates:
            return []
        scores = await asyncio.to_thread(self._reranker.score, query, [hit.content for hit in candidates])
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True)
        return [hit.model_copy(update={"rerank_score": score}) for hit, score in ranked[: self._rerank_top_n]]
