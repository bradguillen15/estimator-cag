from pydantic import BaseModel, Field

from app.schemas.estimations import EstimationResponse


class SessionCreatedResponse(BaseModel):
    session_id: str = Field(description="Send it on every later request of this conversation.")


class ProjectMetadata(BaseModel):
    """Facts about the project in progress. Everything is optional: a new session knows nothing.

    Lives in ``schemas`` because both the session store and the prompt loader use it.
    """

    project_name: str | None = None
    assumed_team_size: int | None = Field(default=None, ge=1)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None

    def is_empty(self) -> bool:
        return self == ProjectMetadata()


class SessionEstimationResponse(EstimationResponse):
    """A session turn: the estimate plus the session memory after this turn."""

    project_metadata: ProjectMetadata
    history_turns: int = Field(description="Turns kept in the history window after this one.")
