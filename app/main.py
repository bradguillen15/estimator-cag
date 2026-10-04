from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.exceptions import (
    AttachmentError,
    InputRejectedError,
    LLMProviderError,
    PromptTemplateError,
    SessionNotFoundError,
    UnknownPromptVersionError,
)
from app.logging_config import configure_logging
from app.routers import estimations, sessions

configure_logging()

app = FastAPI(
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
