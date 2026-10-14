"""Response cache contract and the exact-match cache key.

Implementations never raise: a cache that cannot be reached behaves as a permanent miss, so a
cache outage degrades to "no cache" and never fails a request.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.schemas.estimations import Audience, EstimationRequest


@dataclass(frozen=True)
class CachedAnswer:
    text: str
    model: str | None = None  # model that generated it, when known


class ResponseCache(Protocol):
    def get(self, key: str) -> CachedAnswer | None: ...

    def set(self, key: str, answer: CachedAnswer) -> None: ...


class NoOpCache:
    """Used when caching is disabled: always a miss, stores nothing."""

    def get(self, key: str) -> CachedAnswer | None:
        return None

    def set(self, key: str, answer: CachedAnswer) -> None:
        return None


def make_cache_key(request: EstimationRequest, prompt_version: str, models: Sequence[str]) -> str:
    """SHA-256 over everything that shapes the answer.

    ``request.audience`` must be the *resolved* tier (the service sets it), because the tier changes
    the answer. ``request.description`` must be the sanitized one (after PII redaction), so equal requests that
    only differ in redacted data share an entry and raw PII never reaches the cache key material.
    """
    payload = json.dumps(
        {
            "prompt_version": prompt_version,
            "models": list(models),
            "description": request.description.strip(),
            "project_type": request.project_type.value,
            "detail_level": request.detail_level.value,
            "output_format": request.output_format.value,
            "language": request.language.value,
            # Only for a non-default tier, so existing keys stay valid and the default is unchanged.
            **({"audience": request.audience.value} if request.audience not in (None, Audience.DEFAULT) else {}),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"estimation:exact:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
