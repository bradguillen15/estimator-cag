"""The Critic: an independent LLM audit of a Markdown estimate.

One extra call per actor attempt, through ``LLMProvider.complete`` (the provider contract does not
grow). It never mutates anything and never decides what happens next; that is the ReviewLoop's job.

Its issue messages are re-injected into the actor's system prompt and derive from user text, so they get
the same treatment as extracted metadata: an injection check on every message, a length cap (schema),
and a template that marks them as data.

Reviewing never breaks a request: on any failure (provider error, invalid JSON, schema mismatch) the
estimate is accepted as it is and a warning is logged.
"""

import json
import re

import structlog
from pydantic import ValidationError

from app.exceptions import LLMProviderError
from app.prompts.loader import render_critic_prompt
from app.schemas.critic import CriticFeedback
from app.services.guardrails.input import prompt_injection_pattern
from app.services.llm.base import LLMProvider

logger = structlog.get_logger()

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class Critic:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def review(self, description: str, estimate: str) -> CriticFeedback:
        """The verdict on ``estimate``; ``accept`` (no issues) when the review itself fails."""
        system, user = render_critic_prompt(description, estimate)
        try:
            raw = self._provider.complete(system, user)
            feedback = CriticFeedback.model_validate_json(_FENCE_RE.sub("", raw.strip()))
        except (LLMProviderError, ValidationError, json.JSONDecodeError) as exc:
            logger.warning("critic_failed_fallback_accept", error_type=type(exc).__name__)
            return CriticFeedback(verdict="accept")
        return self._drop_unsafe_issues(feedback)

    @staticmethod
    def _drop_unsafe_issues(feedback: CriticFeedback) -> CriticFeedback:
        safe = [issue for issue in feedback.issues if prompt_injection_pattern(issue.message) is None]
        if len(safe) == len(feedback.issues):
            return feedback
        logger.warning("critic_issue_rejected", reason="prompt_injection", dropped=len(feedback.issues) - len(safe))
        # Rebuilding re-runs the coherence check: a verdict that lost its blocking issues becomes ``accept``.
        return CriticFeedback(verdict=feedback.verdict, issues=safe)
