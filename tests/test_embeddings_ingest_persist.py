"""Session 8: POST /embeddings/ingest persists one document + its chunks in one transaction (fake store)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_embedding_ingest_service
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import EMBEDDING_DIM, OpenAIEmbedder
from app.embedding_pipeline.ingest_service import EmbeddingIngestService
from app.main import app
from tests.fakes_vector_store import FakeChunkStore

_SAMPLE = Path(__file__).resolve().parent.parent / "data" / "budgets_sample.json"


class _FakeEmbeddings:
    """``client.embeddings`` double: counts calls, returns 1536-dim vectors or raises.

    With ``store``, it records how many transactions were open while it ran.
    """

    def __init__(self, *, fail: bool = False, store: FakeChunkStore | None = None) -> None:
        self.calls = 0
        self.open_transactions_seen: list[int] = []
        self._fail = fail
        self._store = store

    def create(self, model: str, input: list[str]) -> SimpleNamespace:
        self.calls += 1
        if self._store is not None:
            self.open_transactions_seen.append(self._store.open_transactions)
        if self._fail:
            raise RuntimeError("embeddings API down")
        return SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[0.1] * EMBEDDING_DIM) for i in range(len(input))]
        )


def _budget() -> dict:
    return json.loads(_SAMPLE.read_text())[0]


def _payload(source_path: str = "data/budgets_sample.json::BUD-2024-001") -> dict:
    return {"source_path": source_path, "document_type": "historical_budget", "content": _budget()}


def _client(store: FakeChunkStore, embeddings: _FakeEmbeddings) -> TestClient:
    embedder = OpenAIEmbedder(client=SimpleNamespace(embeddings=embeddings))  # type: ignore[arg-type]
    service = EmbeddingIngestService(chunker=JSONStructuralChunker(), embedder=embedder, store=store)
    app.dependency_overrides[get_embedding_ingest_service] = lambda: service
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_ingest_persists_document_and_chunks_and_returns_metrics() -> None:
    store, embeddings = FakeChunkStore(), _FakeEmbeddings()

    response = _client(store, embeddings).post("/embeddings/ingest", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"document_id", "chunks_created", "embedding_dimension", "ingestion_time_ms"}
    assert body["document_id"] == store.documents[0].id
    assert body["chunks_created"] == len(_budget()["components"]) == len(store.documents[0].chunks)
    assert body["embedding_dimension"] == 1536
    assert embeddings.calls == 1  # one batched embeddings.create, not one per chunk


def test_duplicate_source_path_returns_409_with_existing_id_and_skips_embedding() -> None:
    store, embeddings = FakeChunkStore(), _FakeEmbeddings()
    client = _client(store, embeddings)
    first = client.post("/embeddings/ingest", json=_payload()).json()

    response = client.post("/embeddings/ingest", json=_payload())

    assert response.status_code == 409
    assert response.json() == {"detail": "Document already ingested", "document_id": first["document_id"]}
    assert embeddings.calls == 1
    assert len(store.documents) == 1


def test_embedder_failure_leaves_no_document() -> None:
    store = FakeChunkStore()

    response = _client(store, _FakeEmbeddings(fail=True)).post("/embeddings/ingest", json=_payload())

    assert response.status_code == 500
    assert store.documents == []


def test_no_transaction_is_open_during_the_embeddings_call() -> None:
    store = FakeChunkStore()
    embeddings = _FakeEmbeddings(store=store)

    response = _client(store, embeddings).post("/embeddings/ingest", json=_payload())

    assert response.status_code == 200
    assert embeddings.open_transactions_seen == [0]


def test_concurrent_duplicate_rejected_by_unique_index_is_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a second ingest that passes the fast-path check (race) still gets 409, not a duplicate."""
    store, embeddings = FakeChunkStore(), _FakeEmbeddings()
    client = _client(store, embeddings)
    first = client.post("/embeddings/ingest", json=_payload()).json()

    async def _check_misses(self: object, source_path: str) -> None:
        return None

    monkeypatch.setattr("tests.fakes_vector_store._FakeTransaction.find_document_id", _check_misses)

    response = client.post("/embeddings/ingest", json=_payload())

    assert response.status_code == 409
    assert response.json() == {"detail": "Document already ingested", "document_id": first["document_id"]}
    assert len(store.documents) == 1


def test_invalid_budget_is_rejected_before_any_work() -> None:
    store, embeddings = FakeChunkStore(), _FakeEmbeddings()
    payload = _payload()
    payload["content"]["components"] = []

    response = _client(store, embeddings).post("/embeddings/ingest", json=payload)

    assert response.status_code == 422
    assert embeddings.calls == 0


def test_missing_openai_key_returns_500() -> None:
    app.dependency_overrides[get_embedding_ingest_service] = lambda: None

    response = TestClient(app).post("/embeddings/ingest", json=_payload())

    assert response.status_code == 500
