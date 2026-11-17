"""Cross-encoder reranker wrapper (session 10).

Bi-encoders (the embedding retriever) encode the query and each document SEPARATELY, so relevance is the cosine of
two vectors computed without either side seeing the other: fast, but coarse. A cross-encoder feeds the
``(query, document)`` pair through the model TOGETHER and outputs one relevance score, attending across both texts:
far more accurate, far too slow for the whole corpus. Hence recall-then-rerank: cheap branches recall a wide
candidate set, the cross-encoder rescores only those.

This module is only the wrapper (model loading + pair scoring). The recall width and the final cut are decided by
``SemanticRetriever``. The model loads LAZILY on first use and ``sentence_transformers`` (torch) is imported inside
the loader only, so importing this module, booting the app and running tests never pull torch in.

Ported from the official course repo (``LIDR-academy/ai-engineering``, branch ``session_10``) and adapted: the
model name is passed in by the DI provider instead of read from settings here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import structlog

log = structlog.get_logger()


class Reranker(Protocol):
    """What the retriever needs from a reranker: one relevance score per document, in input order."""

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Relevance of each document to ``query`` (higher = more relevant)."""
        ...


class CrossEncoderReranker:
    """Lazily-loaded cross-encoder that rescores ``(query, document)`` pairs.

    One instance owns one loaded model. Loading is guarded by a lock so two concurrent first requests do not load
    the model twice.
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None  # sentence_transformers.CrossEncoder, loaded on demand
        self._load_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        """Force-load the model now (used by the verify script and by warm-up)."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:  # another thread won the race
                return self._model
            # Imported here, not at module top: keeps the import graph (app startup, unit tests) free of torch
            # until a rerank truly happens.
            from sentence_transformers import CrossEncoder

            started = time.perf_counter()
            self._model = CrossEncoder(self._model_name)
            log.info(
                "reranker_loaded",
                model=self._model_name,
                load_ms=int((time.perf_counter() - started) * 1000),
            )
            return self._model

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Score ``query`` against each document (higher = better), in input order.

        One forward pass over all ``(query, document)`` pairs; sentence-transformers batches internally.
        """
        if not documents:
            return []
        model = self._ensure_loaded()
        pairs = [(query, document) for document in documents]
        started = time.perf_counter()
        scores = model.predict(pairs)
        log.info(
            "reranker_scored",
            model=self._model_name,
            pairs=len(pairs),
            score_ms=int((time.perf_counter() - started) * 1000),
        )
        return [float(score) for score in scores]

    def rerank(
        self,
        query: str,
        candidates: list,
        *,
        top_n: int,
        text_of: Callable[[Any], str] = lambda candidate: candidate.content,
    ) -> list:
        """Reorder ``candidates`` by cross-encoder score and keep the best ``top_n``.

        ``text_of`` extracts the document text from a candidate (default: a ``.content`` attribute), so this works
        for schema objects, ORM rows or plain dicts. Equal scores keep their recall order (stable sort).
        """
        if not candidates:
            return []
        scores = self.score(query, [text_of(candidate) for candidate in candidates])
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True)
        return [candidate for candidate, _score in ranked[:top_n]]
