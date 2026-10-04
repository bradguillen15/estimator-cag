from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import (
    get_estimation_service,
    get_prompt_version,
    get_safe_session_request,
    get_session,
    get_session_store,
)
from app.schemas.sessions import SessionCreatedResponse, SessionEstimationResponse
from app.services.estimation_service import EstimationService, SessionTurn
from app.services.sessions import Session, SessionStore

router = APIRouter(tags=["sessions"])

Store = Annotated[SessionStore, Depends(get_session_store)]
Service = Annotated[EstimationService, Depends(get_estimation_service)]
PromptVersion = Annotated[str, Depends(get_prompt_version)]
CurrentSession = Annotated[Session, Depends(get_session)]
# Multipart transcript + attachments, after the session lookup, extraction and input guardrails.
SafeSessionTurn = Annotated[SessionTurn, Depends(get_safe_session_request)]


@router.post("/sessions", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_session(store: Store) -> SessionCreatedResponse:
    return SessionCreatedResponse(session_id=store.create().session_id)


# Domain errors (unknown session, bad attachment, LLM failure…) are mapped by the handlers in main.py.
@router.post("/sessions/{session_id}/estimate", response_model=SessionEstimationResponse)
def create_session_estimate(
    turn: SafeSessionTurn,
    session: CurrentSession,
    service: Service,
    prompt_version: PromptVersion,
) -> SessionEstimationResponse:
    text = service.generate_for_session(turn, session, prompt_version)
    return SessionEstimationResponse(
        text=text,
        prompt_version=prompt_version,
        project_metadata=session.metadata,
        history_turns=len(session.history),
    )
