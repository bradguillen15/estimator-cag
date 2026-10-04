"""Shared fixtures. The real LLM is never called: tests use fakes at its boundary."""

import os

# app.config reads the environment at import time, so pin deterministic, offline settings first.
# Explicit env vars win over the developer's .env, so a real key can never be picked up.
os.environ.update(
    {
        "OPENAI_API_KEY": "test-key",
        "ANTHROPIC_API_KEY": "test-key",
        "APP_ENV": "development",
        "LOG_LEVEL": "WARNING",
        # Optional features off regardless of the developer's .env; tests opt in explicitly.
        "MODERATION_ENABLED": "false",
        "CACHE_ENABLED": "false",
        "SEMANTIC_CACHE_ENABLED": "false",
    }
)

from collections.abc import Iterator  # noqa: E402

import litellm  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import get_estimation_service, get_session_store  # noqa: E402
from app.main import app  # noqa: E402
from app.services.cache.base import CachedAnswer  # noqa: E402
from app.services.estimation_service import EstimationService  # noqa: E402
from app.services.llm.base import GenerationMetrics  # noqa: E402
from app.services.sessions import SessionStore  # noqa: E402

VALID_REQUEST: dict[str, str] = {
    "description": "Portal interno para reservar salas con calendario y avisos por email.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "line_items",
}


@pytest.fixture(autouse=True)
def _forbid_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: any code path that reaches real LiteLLM completion/moderation/embedding fails."""

    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A test tried to call a real LLM API")

    monkeypatch.setattr(litellm, "completion", _blocked)
    monkeypatch.setattr(litellm, "moderation", _blocked)
    monkeypatch.setattr(litellm, "embedding", _blocked)


class FakeProvider:
    """In-memory ``StreamingLLMProvider``: records prompts and replays a scripted answer."""

    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        text: str = "## Estimación: Demo\n\n**Total estimado: 40 horas**",
        tokens: list[str] | None = None,
        error: Exception | None = None,
        fail_after: int | None = None,
    ) -> None:
        self.text = text
        self.tokens = tokens if tokens is not None else ["## Estimación", ": Demo", "\n\nTotal"]
        self.error = error
        self.fail_after = fail_after
        self.calls: list[tuple[str, str]] = []
        self.message_calls: list[list[dict[str, str]]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.error:
            raise self.error
        return self.text

    def complete_messages(self, messages: list[dict[str, str]]) -> str:
        """Also recorded in ``calls`` as ``(system, last user message)``."""
        self.message_calls.append(messages)
        return self.complete(messages[0]["content"], messages[-1]["content"])

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        metrics: GenerationMetrics | None = None,
    ) -> Iterator[str]:
        self.calls.append((system_prompt, user_prompt))
        for index, token in enumerate(self.tokens):
            if self.error and self.fail_after == index:
                raise self.error
            yield token
        if self.error and self.fail_after is None:
            raise self.error
        if metrics is not None:
            metrics.model = self.model
            metrics.input_tokens = 100
            metrics.output_tokens = 20
            metrics.latency_seconds = 0.5


class FakeCache:
    """In-memory ``ResponseCache`` that records every get/set."""

    def __init__(self) -> None:
        self.store: dict[str, CachedAnswer] = {}
        self.gets: list[str] = []
        self.sets: list[str] = []

    def get(self, key: str) -> CachedAnswer | None:
        self.gets.append(key)
        return self.store.get(key)

    def set(self, key: str, answer: CachedAnswer) -> None:
        self.sets.append(key)
        self.store[key] = answer


@pytest.fixture
def fake_cache() -> FakeCache:
    return FakeCache()


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def session_store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def client(fake_provider: FakeProvider, fake_cache: FakeCache, session_store: SessionStore) -> Iterator[TestClient]:
    """API client wired to ``fake_provider``, ``fake_cache`` and a fresh ``session_store`` per test."""
    service = EstimationService(fake_provider, cache=fake_cache)
    app.dependency_overrides[get_estimation_service] = lambda: service
    app.dependency_overrides[get_session_store] = lambda: session_store
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
