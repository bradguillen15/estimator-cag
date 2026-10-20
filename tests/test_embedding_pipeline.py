import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_openai_embedder
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import Budget, Chunk
from app.main import app

_SAMPLE = Path(__file__).resolve().parent.parent / "data" / "budgets_sample.json"


class _FakeEmbeddings:
    """Stands in for ``client.embeddings``: returns one vector per input, optionally reversed or short."""

    def __init__(self, *, reverse: bool = False, drop: int = 0) -> None:
        self._reverse = reverse
        self._drop = drop

    def create(self, model: str, input: list[str]) -> SimpleNamespace:
        data = [SimpleNamespace(index=i, embedding=[float(i)]) for i in range(len(input) - self._drop)]
        return SimpleNamespace(data=list(reversed(data)) if self._reverse else data)


def _embedder(**kwargs: object) -> OpenAIEmbedder:
    return OpenAIEmbedder(client=SimpleNamespace(embeddings=_FakeEmbeddings(**kwargs)))  # type: ignore[arg-type]


def _chunks(n: int) -> list[Chunk]:
    return [Chunk(chunk_id=f"c{i}", text=f"text {i}", token_count=2) for i in range(n)]


def _budgets() -> list[Budget]:
    return [Budget.model_validate(raw) for raw in json.loads(_SAMPLE.read_text())]


def test_chunker_emits_one_chunk_per_component_with_traceable_id() -> None:
    budgets = _budgets()

    chunks = JSONStructuralChunker().chunk(budgets)

    assert len(chunks) == sum(len(b.components) for b in budgets)
    first = budgets[0]
    assert chunks[0].chunk_id == f"{first.budget_id}::{first.components[0].component_id}"
    assert chunks[0].text.startswith(f"[Project: {first.project_summary}]")
    assert chunks[0].token_count > 0


def test_chunker_counts_special_token_text_as_plain_text() -> None:
    budget = _budgets()[0]
    budget.components[0].description = "Reset flow <|endoftext|> notes"

    chunks = JSONStructuralChunker().chunk([budget])

    assert chunks[0].token_count > 0


def test_embed_many_maps_vectors_by_response_index() -> None:
    embedded = _embedder(reverse=True).embed_many(_chunks(3))

    assert [c.embedding for c in embedded] == [[0.0], [1.0], [2.0]]


def test_embed_many_rejects_a_short_response() -> None:
    with pytest.raises(ValueError):
        _embedder(drop=1).embed_many(_chunks(3))


def test_ingest_route_returns_embedded_chunks_and_stats() -> None:
    app.dependency_overrides[get_openai_embedder] = lambda: _embedder()
    try:
        response = TestClient(app).post("/embeddings/ingest", json={"budgets": json.loads(_SAMPLE.read_text())})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["total_chunks"] == len(body["chunks"])
    assert body["stats"]["total_tokens"] > 0
