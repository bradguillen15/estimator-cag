from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import (
    get_estimation_service,
    get_prompt_version,
    get_safe_session_request,
    get_session_store,
)
from app.schemas.estimations import EstimationRequest, EstimationResponse
from app.schemas.sessions import SessionCreatedResponse
from app.services.estimation_service import EstimationService
from app.services.llm.base import GenerationMetrics
from app.services.sessions import SessionStore

router = APIRouter(tags=["sessions"])

Store = Annotated[SessionStore, Depends(get_session_store)]
Service = Annotated[EstimationService, Depends(get_estimation_service)]
PromptVersion = Annotated[str, Depends(get_prompt_version)]
# Multipart transcript + attachments, after the session lookup, extraction and input guardrails.
SafeSessionRequest = Annotated[EstimationRequest, Depends(get_safe_session_request)]


@router.post("/sessions", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_session(store: Store) -> SessionCreatedResponse:
    return SessionCreatedResponse(session_id=store.create().session_id)


# Domain errors (unknown session, bad attachment, LLM failure…) are mapped by the handlers in main.py.
@router.post("/sessions/{session_id}/estimate", response_model=EstimationResponse)
def create_session_estimate(
    body: SafeSessionRequest,
    service: Service,
    prompt_version: PromptVersion,
) -> EstimationResponse:
    metrics = GenerationMetrics(model=service.model)
    text = service.generate(body, prompt_version, metrics=metrics)
    return EstimationResponse(text=text, prompt_version=prompt_version, cache_hit=metrics.cache_hit)
