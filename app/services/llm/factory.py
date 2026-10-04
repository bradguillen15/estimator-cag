"""Builds the LLM provider (LiteLLM) from the ``LLM_MODELS`` setting."""

from app.config import Settings
from app.services.llm.base import EmbeddingProvider, EstimationLLMProvider, ModerationProvider
from app.services.llm.embeddings import LiteLLMEmbedder
from app.services.llm.litellm import LiteLLMProvider
from app.services.llm.moderation import LiteLLMModerator


def _require_key(name: str, value: str | None) -> str:
    """Fails at build time (boot / first use), never in the middle of a request."""
    if not value:
        raise ValueError(f"{name} is required by the configured LLM provider but is not set.")
    return value


def _key_by_prefix(settings: Settings) -> dict[str, tuple[str, str | None]]:
    return {
        "anthropic": ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        "openai": ("OPENAI_API_KEY", settings.openai_api_key),
    }


def get_llm_provider(settings: Settings) -> EstimationLLMProvider:
    key_by_prefix = _key_by_prefix(settings)
    if not settings.llm_models:
        raise ValueError("LLM_MODELS must list at least one '<provider>/<model>' entry.")

    api_keys: dict[str, str] = {}
    for model in settings.llm_models:
        prefix = model.split("/", 1)[0]
        if "/" not in model or prefix not in key_by_prefix:
            raise ValueError(
                f"Unsupported LLM_MODELS entry: {model!r}. "
                f"Use '<provider>/<model>' with a provider in: {', '.join(sorted(key_by_prefix))}"
            )
        env_name, key = key_by_prefix[prefix]
        api_keys[prefix] = _require_key(env_name, key)

    return LiteLLMProvider(
        models=settings.llm_models,
        api_keys=api_keys,
        timeout=settings.llm_timeout,
        retries=settings.llm_retries,
        max_tokens=settings.llm_max_tokens,
    )


def get_moderator(settings: Settings) -> ModerationProvider | None:
    """The moderation backend, or ``None`` when ``MODERATION_ENABLED`` is off."""
    if not settings.moderation_enabled:
        return None
    return LiteLLMModerator(
        api_key=_require_key("OPENAI_API_KEY", settings.openai_api_key),
        timeout=settings.llm_timeout,
        retries=settings.llm_retries,
    )


def get_embedder(settings: Settings) -> EmbeddingProvider:
    """Embeddings for the semantic cache: ``EMBEDDING_MODEL`` is a '<provider>/<model>' entry."""
    key_by_prefix = _key_by_prefix(settings)
    prefix = settings.embedding_model.split("/", 1)[0]
    if "/" not in settings.embedding_model or prefix not in key_by_prefix:
        raise ValueError(
            f"Unsupported EMBEDDING_MODEL: {settings.embedding_model!r}. "
            f"Use '<provider>/<model>' with a provider in: {', '.join(sorted(key_by_prefix))}"
        )
    env_name, key = key_by_prefix[prefix]
    return LiteLLMEmbedder(model=settings.embedding_model, api_key=_require_key(env_name, key))
