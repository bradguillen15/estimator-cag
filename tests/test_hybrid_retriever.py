"""SemanticRetriever configurations A-D with a fake embedder, store and reranker (no torch, no Postgres)."""

import asyncio
from types import SimpleNamespace

import pytest

from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.retriever import RerankerUnavailableError, SemanticRetriever
from app.embedding_pipeline.schemas import EmbeddedChunk
from tests.fakes_vector_store import FakeChunkStore, StoredDocument


class _Embeddings:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, model: str, input: list[str]) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[1.0, 0.0]) for i in range(len(input))])


class _WordReranker:
    """Prefers documents containing the word 'gold'; records its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def score(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, len(documents)))
        return [10.0 if "gold" in doc else 0.0 for doc in documents]


def _chunk(text: str, vector: list[float]) -> EmbeddedChunk:
    return EmbeddedChunk(chunk_id=text, text=text, metadata={}, token_count=1, embedding=vector)


def _store() -> FakeChunkStore:
    # Vector ranking for query vector [1, 0]: near < mid < far < gold. Lexical ("gold payments"): gold, payments.
    chunks = [
        _chunk("near", [1.0, 0.0]),
        _chunk("mid", [1.0, 1.0]),
        _chunk("far gold", [0.0, 1.0]),
        _chunk("payments", [0.1, 1.0]),
    ]
    return FakeChunkStore(documents=[StoredDocument(1, "doc", "historical_budget", {}, chunks)])


def _retriever(embeddings: _Embeddings | None = None, reranker: _WordReranker | None = None, **kwargs) -> SemanticRetriever:
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=embeddings or _Embeddings()))  # type: ignore[arg-type]
    return SemanticRetriever(embedder=embedder, store=_store(), reranker=reranker, **kwargs)


def _search(retriever: SemanticRetriever, **kwargs):
    return asyncio.run(retriever.search(query="gold payments", k=kwargs.pop("k", 3), **kwargs))


def _contents(response) -> list[str]:
    return [hit.content for hit in response.results]


def test_config_a_vector_returns_k_nearest_with_distance_only() -> None:
    response = _search(_retriever(), mode="vector", rerank=False)

    assert _contents(response) == ["near", "mid", "payments"]
    assert response.mode == "vector" and response.rerank is False
    assert all(hit.distance is not None and hit.rrf_score is None and hit.rerank_score is None for hit in response.results)
    assert response.rerank_ms == 0


def test_config_b_hybrid_fuses_both_branches_and_keeps_k() -> None:
    response = _search(_retriever(recall_k=10), mode="hybrid", rerank=False, k=3)

    # vector: near, mid, payments, far gold ; lexical: far gold, payments. The two documents found by both branches
    # (far gold, payments) outrank the vector-only ones.
    assert _contents(response)[:2] == ["far gold", "payments"]
    assert len(response.results) == 3
    assert all(hit.rrf_score is not None and hit.rerank_score is None for hit in response.results)


def test_hybrid_keeps_distance_for_vector_hits_and_none_for_lexical_only() -> None:
    chunks = [_chunk("near", [1.0, 0.0]), _chunk("gold", [0.0, 1.0])]
    store = FakeChunkStore(documents=[StoredDocument(1, "doc", "t", {}, chunks)])
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=_Embeddings()))  # type: ignore[arg-type]
    retriever = SemanticRetriever(embedder=embedder, store=store, recall_k=1)

    response = asyncio.run(retriever.search(query="gold", k=5, mode="hybrid"))

    by_content = {hit.content: hit for hit in response.results}
    assert by_content["near"].distance == pytest.approx(0.0)  # vector-only (recall_k=1)
    assert by_content["gold"].distance is None  # lexical-only


def test_config_c_vector_rerank_recalls_wide_then_cuts_to_top_n() -> None:
    reranker = _WordReranker()

    response = _search(_retriever(reranker=reranker, recall_k=10, rerank_top_n=2), mode="vector", rerank=True, k=1)

    assert reranker.calls == [("gold payments", 4)]  # recalled recall_k (all 4), not k=1
    assert _contents(response)[0] == "far gold"
    assert len(response.results) == 2  # rerank_top_n wins over k
    assert response.results[0].rerank_score == 10.0 and response.rerank is True


def test_config_d_hybrid_rerank_scores_the_fused_candidates() -> None:
    reranker = _WordReranker()

    response = _search(_retriever(reranker=reranker, recall_k=10, rerank_top_n=3), mode="hybrid", rerank=True)

    assert reranker.calls == [("gold payments", 4)]
    assert _contents(response)[0] == "far gold"
    assert all(hit.rrf_score is not None and hit.rerank_score is not None for hit in response.results)


def test_defaults_come_from_the_constructor_when_request_leaves_them_unset() -> None:
    reranker = _WordReranker()
    retriever = _retriever(reranker=reranker, default_mode="hybrid", default_rerank=True, rerank_top_n=1, recall_k=10)

    response = _search(retriever)

    assert response.mode == "hybrid" and response.rerank is True
    assert len(response.results) == 1 and reranker.calls

    explicit = _search(retriever, mode="vector", rerank=False)
    assert explicit.mode == "vector" and explicit.rerank is False and len(explicit.results) == 3


def test_rerank_without_a_reranker_raises_a_clear_error() -> None:
    with pytest.raises(RerankerUnavailableError):
        _search(_retriever(reranker=None), rerank=True)


def test_query_is_embedded_once_and_a_precomputed_vector_skips_embedding() -> None:
    embeddings = _Embeddings()
    retriever = _retriever(embeddings, recall_k=10, default_mode="hybrid")

    _search(retriever)
    assert embeddings.calls == 1

    response = asyncio.run(retriever.search_with_vector(query="gold", query_vector=[1.0, 0.0], k=2))
    assert embeddings.calls == 1 and response.embed_ms == 0 and len(response.results) == 2


def test_empty_corpus_returns_no_results_in_every_configuration() -> None:
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=_Embeddings()))  # type: ignore[arg-type]
    retriever = SemanticRetriever(embedder=embedder, store=FakeChunkStore(), reranker=_WordReranker())

    for mode in ("vector", "hybrid"):
        for rerank in (False, True):
            response = asyncio.run(retriever.search(query="x", k=3, mode=mode, rerank=rerank))
            assert response.results == []
