from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import get_session_store
from app.schemas.sessions import SessionCreatedResponse
from app.services.sessions import SessionStore

router = APIRouter(tags=["sessions"])

Store = Annotated[SessionStore, Depends(get_session_store)]


@router.post("/sessions", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_session(store: Store) -> SessionCreatedResponse:
    return SessionCreatedResponse(session_id=store.create().session_id)
