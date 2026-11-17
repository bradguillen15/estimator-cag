"""CrossEncoderReranker wrapper with a fake model object: sentence_transformers is never imported."""

import sys
from types import SimpleNamespace

from app.embedding_pipeline.reranker import CrossEncoderReranker


class _FakeModel:
    """Scores a pair by how many query words the document shares."""

    def __init__(self) -> None:
        self.calls = 0

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls += 1
        return [float(len(set(q.split()) & set(d.split()))) for q, d in pairs]


def _reranker(model: _FakeModel) -> CrossEncoderReranker:
    reranker = CrossEncoderReranker("fake-model")
    reranker._model = model  # injected: _ensure_loaded returns it without importing sentence_transformers
    return reranker


def test_importing_the_wrapper_does_not_load_torch() -> None:
    assert "sentence_transformers" not in sys.modules


def test_score_keeps_input_order_and_returns_floats() -> None:
    scores = _reranker(_FakeModel()).score("cart checkout", ["cart checkout flow", "hospital", "checkout"])

    assert scores == [2.0, 0.0, 1.0]


def test_score_of_no_documents_does_not_touch_the_model() -> None:
    model = _FakeModel()

    assert _reranker(model).score("q", []) == []
    assert model.calls == 0


def test_rerank_orders_by_score_cuts_to_top_n_and_is_stable_on_ties() -> None:
    candidates = [
        SimpleNamespace(content="hospital"),
        SimpleNamespace(content="cart checkout flow"),
        SimpleNamespace(content="checkout"),
        SimpleNamespace(content="cart"),
    ]

    top = _reranker(_FakeModel()).rerank("cart checkout", candidates, top_n=3)

    assert [c.content for c in top] == ["cart checkout flow", "checkout", "cart"]


def test_rerank_accepts_a_custom_text_extractor_and_empty_input() -> None:
    reranker = _reranker(_FakeModel())

    assert reranker.rerank("a b", [{"t": "a"}, {"t": "a b"}], top_n=1, text_of=lambda c: c["t"]) == [{"t": "a b"}]
    assert reranker.rerank("a", [], top_n=3) == []
