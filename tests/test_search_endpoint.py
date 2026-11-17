"""Session 8: POST /search contract (fake embedder + in-memory store, no live database)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_semantic_retriever
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.retriever import SemanticRetriever
from app.embedding_pipeline.schemas import EmbeddedChunk
from app.main import app
from tests.fakes_vector_store import FakeChunkStore, StoredDocument


class _FixedEmbeddings:
    """Always embeds to ``vector`` (or raises)."""

    def __init__(self, vector: list[float], *, fail: bool = False) -> None:
        self._vector = vector
        self._fail = fail

    def create(self, model: str, input: list[str]) -> SimpleNamespace:
        if self._fail:
            raise RuntimeError("embeddings API down")
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=self._vector) for i in range(len(input))])


def _chunk(text: str, vector: list[float]) -> EmbeddedChunk:
    return EmbeddedChunk(chunk_id=text, text=text, metadata={"tag": text}, token_count=1, embedding=vector)


def _store() -> FakeChunkStore:
    chunks = [_chunk("near", [1.0, 0.0]), _chunk("far", [0.0, 1.0]), _chunk("mid", [1.0, 1.0])]
    return FakeChunkStore(documents=[StoredDocument(1, "doc", "historical_budget", {}, chunks)])


def _client(store: FakeChunkStore, embeddings: _FixedEmbeddings) -> TestClient:
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=embeddings))  # type: ignore[arg-type]
    app.dependency_overrides[get_semantic_retriever] = lambda: SemanticRetriever(embedder=embedder, store=store)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_search_returns_k_hits_ranked_by_distance() -> None:
    response = _client(_store(), _FixedEmbeddings([1.0, 0.0])).post("/search", json={"query": "auth", "k": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "auth" and body["k"] == 2 and body["search_time_ms"] >= 0
    assert [hit["content"] for hit in body["results"]] == ["near", "mid"]
    assert body["results"][0]["distance"] == pytest.approx(0.0)
    assert set(body["results"][0]) == {
        "chunk_id",
        "document_id",
        "chunk_type",
        "content",
        "distance",
        "rrf_score",
        "rerank_score",
        "metadata",
    }
    assert body["mode"] == "vector" and body["rerank"] is False


def test_k_defaults_to_five() -> None:
    response = _client(_store(), _FixedEmbeddings([1.0, 0.0])).post("/search", json={"query": "auth"})

    assert response.json()["k"] == 5


def test_empty_corpus_is_200_with_no_results() -> None:
    response = _client(FakeChunkStore(), _FixedEmbeddings([1.0, 0.0])).post("/search", json={"query": "x"})

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "x", "k": 0}, {"query": "x", "k": 51}])
def test_invalid_request_is_422(payload: dict) -> None:
    response = _client(_store(), _FixedEmbeddings([1.0, 0.0])).post("/search", json=payload)

    assert response.status_code == 422


def test_embedder_failure_is_500() -> None:
    response = _client(_store(), _FixedEmbeddings([1.0, 0.0], fail=True)).post("/search", json={"query": "x"})

    assert response.status_code == 500


def test_missing_openai_key_is_500() -> None:
    app.dependency_overrides[get_semantic_retriever] = lambda: None

    response = TestClient(app).post("/search", json={"query": "x"})

    assert response.status_code == 500


def _hybrid_client(reranker: object | None = None) -> TestClient:
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=_FixedEmbeddings([1.0, 0.0])))  # type: ignore[arg-type]
    retriever = SemanticRetriever(embedder=embedder, store=_store(), reranker=reranker)  # type: ignore[arg-type]
    app.dependency_overrides[get_semantic_retriever] = lambda: retriever
    return TestClient(app)


class _ReverseReranker:
    def score(self, query: str, documents: list[str]) -> list[float]:
        return [float(index) for index, _ in enumerate(documents)]


def test_hybrid_mode_echoes_mode_and_timings_and_fusion_scores() -> None:
    response = _hybrid_client().post("/search", json={"query": "near", "k": 2, "mode": "hybrid"})

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "hybrid" and body["rerank"] is False
    assert {"embed_ms", "retrieval_ms", "rerank_ms"} <= set(body)
    assert all(hit["rrf_score"] is not None for hit in body["results"])


def test_rerank_param_applies_the_reranker() -> None:
    response = _hybrid_client(_ReverseReranker()).post("/search", json={"query": "x", "k": 3, "rerank": True})

    body = response.json()
    assert body["rerank"] is True
    assert body["results"][0]["rerank_score"] is not None
    assert [hit["content"] for hit in body["results"]][0] == "far"  # the scorer favours the last recalled candidate


def test_rerank_without_reranker_is_500() -> None:
    response = _hybrid_client(None).post("/search", json={"query": "x", "rerank": True})

    assert response.status_code == 500
    assert response.json()["detail"] == "Reranking is not available."


def test_unknown_mode_is_422() -> None:
    response = _hybrid_client().post("/search", json={"query": "x", "mode": "fuzzy"})

    assert response.status_code == 422
