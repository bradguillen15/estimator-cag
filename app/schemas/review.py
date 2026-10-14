"""Response contract of the critic review loop endpoint."""

from pydantic import BaseModel, Field

from app.schemas.critic import CriticIssue, CriticVerdict
from app.schemas.estimations import Audience


class ReviewIteration(BaseModel):
    """What the Critic said about one actor attempt."""

    attempt: int = Field(ge=1, description="1-based actor attempt.")
    verdict: CriticVerdict
    issues: list[CriticIssue] = Field(default_factory=list)


class ReviewedEstimateResponse(BaseModel):
    estimation: str
    prompt_version: str
    audience: Audience = Audience.DEFAULT
    audience_rule: str = "default"
    final_verdict: CriticVerdict = Field(
        description="accept: the Critic approved it. needs_iteration: budget exhausted with open issues. "
        "reject: the Critic judged the estimate fundamentally wrong (the last draft is returned anyway)."
    )
    iterations: list[ReviewIteration]
