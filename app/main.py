from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.dependencies import get_catalog
from app.embedding_pipeline.router import router as embeddings_router
from app.embedding_pipeline.search_router import router as search_router
from app.exceptions import (
    AttachmentError,
    InputRejectedError,
    IngestionJobNotFoundError,
    IngestionSourceNotFoundError,
    IngestionSourceNotIncludedError,
    LLMProviderError,
    PromptTemplateError,
    SessionNotFoundError,
    UnknownPromptVersionError,
)
from app.logging_config import configure_logging
from app.routers import estimations, ingestion, sessions

configure_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the data catalog once and log it; a bad catalog never aborts startup."""
    try:
        catalog = get_catalog()
        logger.info(
            "catalog_loaded",
            version=catalog.version,
            sources=len(catalog.sources),
            included=len(catalog.included_sources()),
        )
    except Exception as exc:
        logger.error("catalog_load_failed", error=str(exc)[:400])
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Estimator CAG",
    description=(
        "Software project effort estimation with CAG (Cache-Augmented Generation). "
        "Takes a project description plus type, detail level, output format and response "
        "language, and returns a Markdown estimate guided by curated examples injected "
        "into the system prompt."
    ),
    version="0.1.0",
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid4()),
            endpoint=request.url.path,
        )
        try:
            return await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()


app.add_middleware(RequestContextMiddleware)
app.include_router(estimations.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(ingestion.router)
app.include_router(embeddings_router)
app.include_router(search_router)


# Domain error → HTTP status. Messages are client-safe; provider details stay in the logs.
@app.exception_handler(PromptTemplateError)
async def _prompt_template_error(_: Request, exc: PromptTemplateError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(UnknownPromptVersionError)
async def _unknown_prompt_version_error(_: Request, exc: UnknownPromptVersionError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(InputRejectedError)
async def _input_rejected_error(_: Request, exc: InputRejectedError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AttachmentError)
async def _attachment_error(_: Request, exc: AttachmentError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SessionNotFoundError)
async def _session_not_found_error(_: Request, exc: SessionNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(IngestionSourceNotFoundError)
async def _ingestion_source_not_found(_: Request, exc: IngestionSourceNotFoundError) -> JSONResponse:
    detail = {"reason": exc.reason, "source_name": exc.source_name}
    return JSONResponse(status_code=404, content={"detail": detail})


@app.exception_handler(IngestionJobNotFoundError)
async def _ingestion_job_not_found(_: Request, exc: IngestionJobNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": {"reason": exc.reason, "job_id": str(exc.job_id)}})


@app.exception_handler(IngestionSourceNotIncludedError)
async def _ingestion_source_not_included(_: Request, exc: IngestionSourceNotIncludedError) -> JSONResponse:
    detail = {
        "reason": exc.reason,
        "source_name": exc.source_name,
        "decision": exc.decision,
        "decision_reason": exc.decision_reason,
    }
    return JSONResponse(status_code=400, content={"detail": detail})


@app.exception_handler(LLMProviderError)
async def _llm_provider_error(_: Request, exc: LLMProviderError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Built React UI (web/dist). Mounted last so /api, /health and /docs keep priority.
_WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
