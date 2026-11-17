"""HTTP layer for semantic search (session 8): ``POST /search``.

Validation lives in ``SearchRequest`` (k bounds, mode values -> 422) and the embed + SQL ranking in ``SemanticRetriever``.
An empty corpus is a 200 with no results, not an error.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_semantic_retriever
from app.embedding_pipeline.retriever import RerankerUnavailableError, SemanticRetriever
from app.embedding_pipeline.schemas import SearchRequest, SearchResponse

log = structlog.get_logger()

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    retriever: SemanticRetriever | None = Depends(get_semantic_retriever),
) -> SearchResponse:
    """Search the corpus: vector or hybrid (vector + full-text, RRF), optionally cross-encoder reranked."""
    if retriever is None:
        # No OPENAI_API_KEY configured. Generic message to the client, detail logged.
        log.error("search_failed", reason="retriever_unavailable")
        raise HTTPException(status_code=500, detail="Embedding service is not available.")

    try:
        return await retriever.search(query=request.query, k=request.k, mode=request.mode, rerank=request.rerank)
    except RerankerUnavailableError as exc:
        log.error("search_failed", reason="reranker_unavailable")
        raise HTTPException(status_code=500, detail="Reranking is not available.") from exc
    except Exception as exc:  # noqa: BLE001 — embeddings-API or database failures become a 500.
        log.error("search_failed", reason="search_error", error_type=type(exc).__name__, error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="Failed to run the semantic search.") from exc
