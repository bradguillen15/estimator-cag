from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.review import ReviewIteration
from app.schemas.critic import CriticVerdict
from app.schemas.estimations import Audience, EstimationResponse


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


class TurnPair(BaseModel):
    """One user message and the assistant reply it got, as the history replays them."""

    model_config = ConfigDict(frozen=True)

    user: str
    assistant: str


class HistoryMemory(BaseModel):
    """What survives after turns leave the history window: a running summary and verbatim anchors.

    Lives in ``schemas`` because the session store, the compressor and the prompt loader share it.
    """

    summary: str = ""
    anchors: list[TurnPair] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.summary and not self.anchors


class TurnObservation(BaseModel):
    """Measurements of one session turn, logged as ``turn_observed`` and returned as ``observation``.

    Totals (``tokens_in``, ``tokens_out``, ``cost_usd``) sum the LLM calls of the turn that completed:
    the actor (every attempt on the reviewed route), the critic reviews (reviewed route), the
    metadata extractor and, when turns overflowed the window, the summarizer. A call that raised
    adds nothing; a provider that reports no usage counts as 0. ``latency_ms`` is the wall-clock of
    the whole turn in the service, from the first prompt to the recorded memory.
    """

    turn_index: int = Field(ge=1, description="1-based position in the session; not capped by the history window.")
    session_id: str
    enriched_transcript_chars: int = Field(ge=0, description="Transcript + attachment text sent to the LLM.")
    attachments_total_chars: int = Field(ge=0, description="Raw extracted attachment text (0 without files).")
    messages_in_window: int = Field(ge=0, description="History messages kept after compression.")
    anchors_count: int = Field(ge=0)
    summary_chars: int = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    cache_hit_kind: Literal["none", "exact", "semantic"] = Field(
        description="Always 'none' on session turns: they bypass both response caches by design."
    )
    last_resolved_tier: Audience | None = None


class SessionEstimationResponse(EstimationResponse):
    """A session turn: the estimate plus the session memory after this turn."""

    project_metadata: ProjectMetadata
    history_turns: int = Field(description="Turns kept in the history window after this one.")
    observation: TurnObservation | None = None


class SessionReviewedEstimateResponse(SessionEstimationResponse):
    """A session turn produced by the critic review loop: the turn fields plus the Critic's verdict and trail."""

    final_verdict: CriticVerdict
    iterations: list[ReviewIteration]


class SessionSummary(BaseModel):
    """One row of the session list."""

    session_id: str
    project_name: str | None = None
    history_turns: int = Field(description="Turns kept in the history window.")
    created_at: datetime
    updated_at: datetime


class SessionTurnView(BaseModel):
    """One turn as the UI shows it: what the user typed and the estimate that came back."""

    description: str = Field(description="The transcript as typed, without extracted attachment text.")
    attachment_names: list[str] = Field(default_factory=list)
    estimate: str
    prompt_version: str
    cache_hit: bool = False
    final_verdict: CriticVerdict | None = Field(default=None, description="Set on critic-reviewed turns only.")
    created_at: datetime


class SessionDetail(BaseModel):
    """What the UI needs to resume a session: its memory and its turns (capped by the history window)."""

    session_id: str
    project_metadata: ProjectMetadata
    history_turns: int = Field(description="Turns kept in the history window.")
    turns: list[SessionTurnView] = Field(default_factory=list, description="Oldest first.")
    anchors_count: int = Field(default=0, description="Turns kept verbatim after leaving the window (commitments).")
    summary_chars: int = Field(default=0, description="Length of the running summary of the folded turns.")
    summary: str = Field(default="", description="The running summary of the folded turns.")
    anchors: list[str] = Field(default_factory=list, description="User messages of the anchored turns, verbatim.")
    last_observation: TurnObservation | None = None
    last_audience: Audience | None = Field(default=None, description="Tier of the latest turn (none before the first).")
    last_audience_rule: str | None = Field(default=None, description="Resolver rule that chose it.")
    created_at: datetime
    updated_at: datetime
