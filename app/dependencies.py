"""FastAPI dependency providers (``Depends``); override them in tests via ``dependency_overrides``."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, File, Form, Query, UploadFile
from openai import OpenAI
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.exceptions import UnknownPromptVersionError
from app.persistence.database import build_engine, build_session_factory
from app.persistence.repositories.jobs import sql_jobs_scope
from app.persistence.repositories.mappings import PostgresMappingStore
from app.prompts.loader import PROMPT_VERSION, available_prompt_versions
from app.schemas.estimations import Audience, DetailLevel, EstimationRequest, OutputFormat, ProjectType
from app.services.attachments import MAX_ATTACHMENT_BYTES, Attachment, check_attachment_count
from app.services.cache.factory import get_response_cache
from app.services.cache.semantic import NoOpSemanticCache, SemanticCache, build_semantic_cache
from app.services.review_loop import ReviewLoop
from app.services.critic import Critic
from app.services.estimation_service import EstimationService, SessionTurn
from app.services.guardrails.input import InputGuardrails
from app.services.ingestion.catalog import DataCatalog, load_catalog
from app.services.ingestion.loaders import FileSystemLoader
from app.services.ingestion.orchestrator import IngestionService, JobsScope
from app.services.ingestion.parsers import ParserRegistry, default_registry
from app.services.ingestion.pii import ConsistentPseudonymizer, build_analyzer
from app.services.history_compression import HistoryCompressor
from app.services.llm.base import LLMProvider, ModerationProvider
from app.services.llm.factory import get_critic_provider, get_embedder, get_llm_provider, get_moderator
from app.services.sessions import Session, SessionStore
from app.services.summarizer import ConversationSummarizer

logger = structlog.get_logger()


@lru_cache
def get_chunker() -> JSONStructuralChunker:
    """Stateless structural chunker for the embedding pipeline (Session 7)."""
    return JSONStructuralChunker()


@lru_cache
def get_openai_embedder() -> OpenAIEmbedder | None:
    """OpenAI embedder for the embedding pipeline. ``None`` when no API key is
    configured; the router maps that to a 500. (Named apart from ``get_embedder``,
    the LiteLLM embedder of the semantic cache.)"""
    if not settings.openai_api_key:
        logger.warning("embedder_disabled", reason="no_openai_key")
        return None
    # max_retries=0: OpenAIEmbedder owns the rate-limit retries; the SDK's own 2 would multiply them.
    return OpenAIEmbedder(client=OpenAI(api_key=settings.openai_api_key, max_retries=0))

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


def _get_critic_provider(default: LLMProvider) -> LLMProvider:
    try:
        return get_critic_provider(settings) or default
    except ValueError:
        # Optional feature: a bad CRITIC_MODEL degrades to "reuse the main chain", not a 500 per request.
        logger.warning("critic_model_ignored", reason="config_error")
        return default


@lru_cache
def get_estimation_service() -> EstimationService:
    provider = get_llm_provider(settings)
    return EstimationService(
        provider=provider,
        guardrails=InputGuardrails(moderator=_get_moderator()),
        cache=get_response_cache(settings),
        semantic_cache=_get_semantic_cache(),
        cache_models=tuple(settings.llm_models),
        history_compressor=HistoryCompressor(ConversationSummarizer(provider, settings.session_summary_max_chars)),
        critic=Critic(_get_critic_provider(provider)),
        review_loop=ReviewLoop(settings.review_max_iterations),
    )


@lru_cache
def get_session_store() -> SessionStore:
    """One store per process: ``lru_cache`` makes this the process-local session dict."""
    return SessionStore(max_turns=settings.session_max_turns, max_anchors=settings.session_max_anchors)


def get_session(session_id: str, store: Annotated[SessionStore, Depends(get_session_store)]) -> Session:
    """The session named in the path; ``SessionNotFoundError`` (HTTP 404) before any other work."""
    return store.get(session_id)


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


def get_safe_session_request(
    _session: Annotated[Session, Depends(get_session)],
    transcript: Annotated[str, Form(min_length=20, max_length=20000)],
    project_type: Annotated[ProjectType, Form()],
    detail_level: Annotated[DetailLevel, Form()],
    output_format: Annotated[OutputFormat, Form()],
    service: Annotated[EstimationService, Depends(get_estimation_service)],
    _prompt_version: Annotated[str, Depends(get_prompt_version)],
    language: Annotated[str | None, Form()] = None,
    audience: Annotated[Audience | None, Form(description="Explicit audience tier; omit to infer it.")] = None,
    attachments: Annotated[list[UploadFile] | None, File(description="PDF or Word (.docx) files.")] = None,
) -> SessionTurn:
    """The multipart request (transcript + attachments) after extraction and the input guardrails.

    Same contract as ``get_safe_request``: an unknown session (404), an unusable attachment or a
    guardrail rejection (400) all happen before the endpoint runs. The guardrails see the
    transcript *and* the attachment text, so an instruction hidden in a PDF is rejected too.
    """
    request = EstimationRequest.model_validate(
        {
            "description": transcript,
            "project_type": project_type,
            "detail_level": detail_level,
            "output_format": output_format,
            "language": language,
            "audience": audience,
        }
    )
    uploads = attachments or []
    check_attachment_count(len(uploads))  # before reading any upload stream
    files = [
        # Read one byte past the limit: enough to reject an oversized file without loading it all.
        Attachment(filename=upload.filename or "adjunto", content=upload.file.read(MAX_ATTACHMENT_BYTES + 1))
        for upload in uploads
    ]
    return service.prepare_session_turn(request, files)


# --- Ingestion (Session 6). Nothing below touches the DB, spaCy or disk at import time. ---


@lru_cache
def get_catalog() -> DataCatalog:
    return load_catalog(settings.catalog_path)


@lru_cache
def get_filesystem_loader() -> FileSystemLoader:
    return FileSystemLoader(settings.ingestion_data_root)


@lru_cache
def get_parser_registry() -> ParserRegistry:
    return default_registry()


@lru_cache
def get_db_session_factory() -> sessionmaker[DbSession]:
    """Engine + session factory, built on first use (the engine itself connects lazily)."""
    return build_session_factory(build_engine(settings.database_url))


@lru_cache
def get_jobs_scope() -> JobsScope:
    """Unit of work for jobs: every ``with scope()`` gets its own session, so background runs never share a request session."""
    return sql_jobs_scope(get_db_session_factory())


def get_ingestion_service(
    catalog: Annotated[DataCatalog, Depends(get_catalog)],
    loader: Annotated[FileSystemLoader, Depends(get_filesystem_loader)],
    registry: Annotated[ParserRegistry, Depends(get_parser_registry)],
    jobs_scope: Annotated[JobsScope, Depends(get_jobs_scope)],
) -> IngestionService:
    return IngestionService(catalog=catalog, loader=loader, registry=registry, jobs_scope=jobs_scope)


@contextmanager
def build_pseudonymizer() -> Iterator[ConsistentPseudonymizer]:
    """Pseudonymizer backed by Postgres mappings, for the PII step of the pipeline.

    No endpoint uses it yet. It is a context manager because the mapping store needs an open DB
    session for as long as the pseudonymizer is used; loading the spaCy model happens here, not at import.
    """
    session = get_db_session_factory()()
    try:
        yield ConsistentPseudonymizer(
            analyzer=build_analyzer(settings.presidio_spacy_model),
            mapping_store=PostgresMappingStore(session),
            salt=settings.pseudonym_hash_salt,
            faker_locale=settings.pseudonym_faker_locale,
        )
    finally:
        session.close()
