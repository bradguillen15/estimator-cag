"""Optional features (moderation, semantic cache) degrade on config errors; the main provider does not."""

import pytest
from structlog.testing import capture_logs

from app import dependencies
from app.config import Settings
from app.services.cache.semantic import NoOpSemanticCache


@pytest.fixture(autouse=True)
def _clear_service_cache() -> None:
    dependencies.get_estimation_service.cache_clear()
    yield
    dependencies.get_estimation_service.cache_clear()


def _settings(**overrides: object) -> Settings:
    base = {"anthropic_api_key": "k", "openai_api_key": "k", "llm_models": ["anthropic/claude-x"]}
    return Settings(_env_file=None, **(base | overrides))


def test_missing_openai_key_disables_moderation_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "settings", _settings(moderation_enabled=True, openai_api_key=None))
    with capture_logs() as logs:
        assert dependencies._get_moderator() is None
    assert {"event": "moderation_disabled", "reason": "config_error", "log_level": "warning"} in logs


def test_invalid_embedding_model_falls_back_to_noop_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies, "settings", _settings(semantic_cache_enabled=True, embedding_model="bogus")
    )
    with capture_logs() as logs:
        cache = dependencies._get_semantic_cache()
    assert isinstance(cache, NoOpSemanticCache)
    assert {"event": "semantic_cache_disabled", "reason": "config_error", "log_level": "warning"} in logs


def test_service_still_builds_with_broken_optional_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "settings",
        _settings(
            moderation_enabled=True, semantic_cache_enabled=True, openai_api_key=None, embedding_model="bogus"
        ),
    )
    assert dependencies.get_estimation_service() is not None


def test_main_provider_config_errors_still_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "settings", _settings(anthropic_api_key=None))
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        dependencies.get_estimation_service()


def test_invalid_critic_model_falls_back_to_the_main_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependencies, "settings", _settings(critic_model="gemini/flash"))
    main = object()
    with capture_logs() as logs:
        assert dependencies._get_critic_provider(main) is main
    assert {"event": "critic_model_ignored", "reason": "config_error", "log_level": "warning"} in logs
