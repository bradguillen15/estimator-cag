from pydantic import BaseModel, Field


class SessionCreatedResponse(BaseModel):
    session_id: str = Field(description="Send it on every later request of this conversation.")
