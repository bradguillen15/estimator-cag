"""Structured feedback produced by the Critic (the contract between Critic and ReviewLoop)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

CriticIssueCategory = Literal[
    "math_error",
    "hallucination",
    "scope_mismatch",
    "phase_imbalance",
    "missing_assumption",
    "unrealistic_estimate",
]
CriticIssueSeverity = Literal["critical", "major", "minor"]
CriticVerdict = Literal["accept", "needs_iteration", "reject"]

_BLOCKING = {"critical", "major"}


class CriticIssue(BaseModel):
    category: CriticIssueCategory
    severity: CriticIssueSeverity
    message: str = Field(min_length=1, max_length=500)


class CriticFeedback(BaseModel):
    """The Critic's verdict on one estimate.

    Coherence is enforced by *coercion*, not rejection, because a Critic that contradicts itself must
    never fail the request (see ``Critic.review``): ``needs_iteration`` without a critical/major issue
    is downgraded to ``accept`` (minor issues alone are not worth another actor call), and ``reject``
    without any issue is downgraded to ``accept`` too (a rejection with no stated reason is not actionable).
    """

    verdict: CriticVerdict
    issues: list[CriticIssue] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _coerce_incoherent_verdict(self) -> "CriticFeedback":
        if self.verdict == "needs_iteration" and not any(i.severity in _BLOCKING for i in self.issues):
            self.verdict = "accept"
        elif self.verdict == "reject" and not self.issues:
            self.verdict = "accept"
        return self
