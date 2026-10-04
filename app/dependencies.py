"""FastAPI dependency providers (``Depends``); override them in tests via ``dependency_overrides``."""

from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, Query

from app.config import settings
from app.exceptions import UnknownPromptVersionError
from app.prompts.loader import PROMPT_VERSION, available_prompt_versions
from app.schemas.estimations import EstimationRequest
from app.services.cache.factory import get_response_cache
from app.services.cache.semantic import NoOpSemanticCache, SemanticCache, build_semantic_cache
from app.services.estimation_service import EstimationService
from app.services.guardrails.input import InputGuardrails
from app.services.llm.base import ModerationProvider
from app.services.llm.factory import get_embedder, get_llm_provider, get_moderator
from app.services.sessions import SessionStore

logger = structlog.get_logger()


def _get_semantic_cache() -> SemanticCache:
    if not settings.semantic_cache_enabled:
        return NoOpSemanticCache()
    try:
        embedder = get_embedder(settings)
    except ValueError:
        # Optional feature: a bad embedding config degrades to "no semantic cache", not a 500 per request.
        logger.warning("semantic_cache_disabled", reason="config_error")
        return NoOpSemanticCache()
    return build_semantic_cache(settings, embedder, settings.llm_models)


def _get_moderator() -> ModerationProvider | None:
    try:
        return get_moderator(settings)
    except ValueError:
        # Optional feature: a missing key degrades to "no moderation", not a 500 per request.
        logger.warning("moderation_disabled", reason="config_error")
        return None


@lru_cache
def get_estimation_service() -> EstimationService:
    return EstimationService(
        provider=get_llm_provider(settings),
        guardrails=InputGuardrails(moderator=_get_moderator()),
        cache=get_response_cache(settings),
        semantic_cache=_get_semantic_cache(),
        cache_models=tuple(settings.llm_models),
    )


@lru_cache
def get_session_store() -> SessionStore:
    """One store per process: ``lru_cache`` makes this the process-local session dict."""
    return SessionStore(max_turns=settings.session_max_turns)


def get_prompt_version(
    prompt_version: Annotated[
        str | None,
        Query(description="Prompt version to run (a folder under app/prompts/estimation/). Defaults to the active one."),
    ] = None,
) -> str:
    """The effective prompt version; unknown or malformed values are an HTTP 422 before any other work.

    Checked against the versions found on disk, so values such as ``../x`` never reach the loader.
    """
    if prompt_version is None:
        return PROMPT_VERSION
    if prompt_version not in available_prompt_versions():
        available = ", ".join(available_prompt_versions())
        raise UnknownPromptVersionError(
            f"Versión de prompt desconocida: usa una de {available}."
        )
    return prompt_version


def get_safe_request(
    body: EstimationRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    _prompt_version: Annotated[str, Depends(get_prompt_version)],
) -> EstimationRequest:
    """The request after the input guardrails.

    A dependency runs before the endpoint (and before any streaming response starts), so a
    rejection is a plain HTTP 400 on both ``/estimate`` and ``/estimate/stream``. The prompt
    version is validated first, so an invalid one never reaches the guardrails.
    """
    return service.prepare(body)
