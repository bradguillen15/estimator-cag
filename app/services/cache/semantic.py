"""Semantic response cache: near-duplicate descriptions reuse an earlier answer.

Two requests match when they share the same *bucket* (prompt version, type, detail, format and
language: the rendered prompt would differ otherwise) and their description embeddings have a
cosine similarity of at least ``threshold``. With ``log_only`` the lookup still runs and logs the
score but never returns a hit, to calibrate the threshold on real traffic before enabling it.

The embedding is computed once per request (in ``lookup``) and reused by ``store``.
Needs Redis Stack (RediSearch); vanilla Redis fails at index creation and the cache stays off.

The bucket also carries a short hash of the configured model list, so changing ``LLM_MODELS``
never serves another model's answers. A setup failure is permanent for the process (the service
is built once): restart the app to retry. There is deliberately no retry machinery.
"""

import hashlib
import json
from collections.abc import Sequence
from array import array
from dataclasses import dataclass
from typing import Any, Protocol

import redis
import structlog
from redisvl.index import SearchIndex
from redisvl.query import VectorQuery
from redisvl.query.filter import Tag

from app.config import Settings
from app.schemas.estimations import Audience, EstimationRequest
from app.services.cache.base import CachedAnswer
from app.services.llm.base import EmbeddingProvider

logger = structlog.get_logger()


@dataclass(frozen=True)
class SemanticLookup:
    """Outcome of a lookup. ``vector`` is kept so ``store`` does not embed the text again."""

    bucket: str
    vector: list[float] | None = None
    answer: CachedAnswer | None = None


class SemanticCache(Protocol):
    def lookup(self, request: EstimationRequest, prompt_version: str) -> SemanticLookup: ...

    def store(self, lookup: SemanticLookup, answer: CachedAnswer) -> None: ...


def models_scope(models: Sequence[str]) -> str:
    """Short, order-sensitive fingerprint of the configured model list."""
    return hashlib.sha256("|".join(models).encode()).hexdigest()[:8]


def make_bucket(request: EstimationRequest, prompt_version: str) -> str:
    # ``request.audience`` is the resolved tier: a different tier is a different answer, so it must
    # not share a bucket. The default adds nothing, which keeps existing buckets valid.
    bucket = (
        f"{prompt_version}:{request.project_type.value}:{request.detail_level.value}"
        f":{request.output_format.value}:{request.language.value}"
    )
    if request.audience not in (None, Audience.DEFAULT):
        bucket += f":{request.audience.value}"
    return bucket


class NoOpSemanticCache:
    """Used when the semantic cache is disabled or could not be set up."""

    def lookup(self, request: EstimationRequest, prompt_version: str) -> SemanticLookup:
        return SemanticLookup(bucket="")

    def store(self, lookup: SemanticLookup, answer: CachedAnswer) -> None:
        return None


def _to_bytes(vector: list[float]) -> bytes:
    """RediSearch stores vectors as float32 bytes."""
    return array("f", vector).tobytes()


def _schema(name: str, prefix: str, dims: int) -> dict[str, Any]:
    return {
        "index": {"name": name, "prefix": prefix, "storage_type": "hash"},
        "fields": [
            {"name": "bucket", "type": "tag"},
            {"name": "answer_json", "type": "text"},
            {
                "name": "embedding",
                "type": "vector",
                "attrs": {"dims": dims, "distance_metric": "cosine", "algorithm": "flat"},
            },
        ],
    }


class RedisSemanticCache:
    """Vector-similarity cache on redisvl + Redis Stack. Never raises: failures are misses."""

    def __init__(
        self,
        index: SearchIndex,
        embedder: EmbeddingProvider,
        dims: int,
        threshold: float,
        ttl: int,
        log_only: bool,
        models: Sequence[str] = (),
    ) -> None:
        self._scope = models_scope(models)
        self._index = index
        self._embedder = embedder
        self._dims = dims
        self._threshold = threshold
        self._ttl = ttl
        self._log_only = log_only

    def lookup(self, request: EstimationRequest, prompt_version: str) -> SemanticLookup:
        bucket = f"{make_bucket(request, prompt_version)}:{self._scope}"
        try:
            vector = self._embedder.embed(request.description)
            if len(vector) != self._dims:
                logger.warning("semantic_cache_dims_mismatch", expected=self._dims, got=len(vector))
                return SemanticLookup(bucket=bucket)
            query = VectorQuery(
                vector=_to_bytes(vector),
                vector_field_name="embedding",
                return_fields=["answer_json"],
                num_results=1,
                return_score=True,
                filter_expression=Tag("bucket") == bucket,
            )
            results = self._index.query(query)
        except Exception as exc:
            logger.warning("semantic_cache_lookup_failed", error_type=type(exc).__name__)
            return SemanticLookup(bucket=bucket)

        if not results:
            logger.info("semantic_cache_miss", bucket=bucket, reason="empty_bucket")
            return SemanticLookup(bucket=bucket, vector=vector)

        # redisvl returns cosine *distance* (0 = identical); similarity = 1 - distance.
        similarity = 1.0 - float(results[0].get("vector_distance", 1.0))
        if similarity < self._threshold:
            logger.info("semantic_cache_miss", bucket=bucket, reason="below_threshold", similarity=round(similarity, 4))
            return SemanticLookup(bucket=bucket, vector=vector)
        if self._log_only:
            logger.info("semantic_cache_hit_log_only", bucket=bucket, similarity=round(similarity, 4))
            return SemanticLookup(bucket=bucket, vector=vector)

        try:
            data = json.loads(results[0]["answer_json"])
            answer = CachedAnswer(text=data["text"], model=data.get("model"))
        except Exception as exc:
            logger.warning("semantic_cache_decode_failed", error_type=type(exc).__name__)
            return SemanticLookup(bucket=bucket, vector=vector)
        logger.info("semantic_cache_hit", bucket=bucket, similarity=round(similarity, 4))
        return SemanticLookup(bucket=bucket, vector=vector, answer=answer)

    def store(self, lookup: SemanticLookup, answer: CachedAnswer) -> None:
        if lookup.vector is None:  # the embedding failed or was skipped: nothing to index
            return
        record = {
            "bucket": lookup.bucket,
            "answer_json": json.dumps({"text": answer.text, "model": answer.model}),
            "embedding": _to_bytes(lookup.vector),
        }
        try:
            self._index.load([record], ttl=self._ttl)
            logger.info("semantic_cache_stored", bucket=lookup.bucket, ttl=self._ttl)
        except Exception as exc:
            logger.warning("semantic_cache_store_failed", error_type=type(exc).__name__)


def build_semantic_cache(settings: Settings, embedder: EmbeddingProvider, models: Sequence[str] = ()) -> SemanticCache:
    """A Redis semantic cache, or a no-op when the setup fails (logged). Call it only when enabled."""
    try:
        # One index per embedding model: vectors from different models must never be compared.
        suffix = hashlib.sha256(settings.embedding_model.encode()).hexdigest()[:8]
        name = f"estimation_semantic_{suffix}"
        index = SearchIndex.from_dict(_schema(name, f"estimation:semantic:{suffix}", settings.embedding_dims))
        index.set_client(redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2))
        index.create(overwrite=False)  # no-op when it already exists
    except Exception as exc:
        logger.warning("semantic_cache_disabled", reason="setup_failed", error_type=type(exc).__name__)
        return NoOpSemanticCache()
    return RedisSemanticCache(
        index,
        embedder,
        dims=settings.embedding_dims,
        threshold=settings.semantic_cache_threshold,
        ttl=settings.semantic_cache_ttl,
        log_only=settings.semantic_cache_log_only,
        models=models,
    )
