"""LLM provider contract.

Every provider returns text and raises ``LLMProviderError`` on any failure (never ``None``
or an empty string). SDK types never leave the provider's own module.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass
class GenerationMetrics:
    """Metrics of the last LLM call (filled in when the stream finishes)."""

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    cache_hit: bool = False  # answered from the response cache, no LLM call


@dataclass
class UsageTotals:
    """Tokens and cost summed over several LLM calls (one session turn makes more than one).

    Calls that raised are not counted, and a call whose provider reported no usage adds nothing.
    """

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, metrics: GenerationMetrics) -> None:
        self.calls += 1
        self.input_tokens += metrics.input_tokens or 0
        self.output_tokens += metrics.output_tokens or 0
        self.cost_usd += metrics.cost_usd or 0.0


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system_prompt: str, user_prompt: str, metrics: GenerationMetrics | None = None) -> str: ...


class StreamingLLMProvider(LLMProvider, Protocol):
    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        metrics: GenerationMetrics | None = None,
    ) -> Iterator[str]: ...


class ChatLLMProvider(LLMProvider, Protocol):
    """Multi-turn completion: a full ``messages`` list (system first, then user/assistant turns).

    Separate from ``LLMProvider`` (ISP): only session turns replay a conversation.
    """

    def complete_messages(self, messages: list[dict[str, str]], metrics: GenerationMetrics | None = None) -> str: ...


class EstimationLLMProvider(StreamingLLMProvider, ChatLLMProvider, Protocol):
    """Everything ``EstimationService`` uses: single-shot, streaming and multi-turn calls."""


def complete_tracked(
    provider: LLMProvider, system_prompt: str, user_prompt: str, usage: UsageTotals | None = None
) -> str:
    """``provider.complete`` that adds the call's metrics to ``usage`` (a plain call when it is ``None``)."""
    if usage is None:
        return provider.complete(system_prompt, user_prompt)
    metrics = GenerationMetrics(model=provider.model)
    text = provider.complete(system_prompt, user_prompt, metrics=metrics)
    usage.add(metrics)
    return text


def complete_messages_tracked(
    provider: ChatLLMProvider, messages: list[dict[str, str]], usage: UsageTotals | None = None
) -> str:
    """``provider.complete_messages`` that adds the call's metrics to ``usage``."""
    if usage is None:
        return provider.complete_messages(messages)
    metrics = GenerationMetrics(model=provider.model)
    text = provider.complete_messages(messages, metrics=metrics)
    usage.add(metrics)
    return text


class ModerationProvider(Protocol):
    """Content moderation: returns the flagged category names (empty list = allowed)."""

    def flagged_categories(self, text: str) -> list[str]: ...


class EmbeddingProvider(Protocol):
    """Turns text into an embedding vector. Raises on any failure (callers decide to degrade)."""

    def embed(self, text: str) -> list[float]: ...
