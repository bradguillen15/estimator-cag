"""Folds turns that left the history window into a bounded, running summary.

One extra, small LLM call per overflow, through ``LLMProvider.complete`` (the provider contract
does not grow). The summary ends up in the *system* prompt of later turns and derives from user
text, so it gets the same treatment as extracted metadata: a prompt-injection check, a hard
length cap, and a template that marks it as data.

Summarizing never breaks a turn: on any failure the previous summary is kept and a warning logged.
"""

from collections.abc import Sequence

import structlog

from app.exceptions import LLMProviderError
from app.prompts.loader import render_summary_prompt
from app.schemas.sessions import TurnPair
from app.services.guardrails.input import prompt_injection_pattern
from app.services.llm.base import LLMProvider

logger = structlog.get_logger()

DEFAULT_MAX_CHARS = 2_000


class ConversationSummarizer:
    def __init__(self, provider: LLMProvider, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        self._provider = provider
        self._max_chars = max_chars

    def summarize(self, previous: str, evicted: Sequence[TurnPair], language: str = "es") -> str:
        """The updated summary, or ``previous`` when there is nothing to fold or the call fails."""
        if not evicted:
            return previous
        system, user = render_summary_prompt(previous, evicted, language, self._max_chars)
        try:
            raw = self._provider.complete(system, user)
        except LLMProviderError as exc:
            logger.warning("summary_failed", error_type=type(exc).__name__)
            return previous
        summary = raw.strip()[: self._max_chars].strip()
        if not summary:
            logger.warning("summary_failed", error_type="EmptySummary")
            return previous
        if prompt_injection_pattern(summary) is not None:
            logger.warning("summary_rejected", reason="prompt_injection")
            return previous
        logger.info("summary_updated", folded_turns=len(evicted), summary_chars=len(summary))
        return summary
