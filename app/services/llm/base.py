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


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


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

    def complete_messages(self, messages: list[dict[str, str]]) -> str: ...


class EstimationLLMProvider(StreamingLLMProvider, ChatLLMProvider, Protocol):
    """Everything ``EstimationService`` uses: single-shot, streaming and multi-turn calls."""


class ModerationProvider(Protocol):
    """Content moderation: returns the flagged category names (empty list = allowed)."""

    def flagged_categories(self, text: str) -> list[str]: ...


class EmbeddingProvider(Protocol):
    """Turns text into an embedding vector. Raises on any failure (callers decide to degrade)."""

    def embed(self, text: str) -> list[float]: ...
