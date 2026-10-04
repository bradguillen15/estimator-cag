"""Domain exceptions. The exception handlers in main.py translate them to HTTP responses."""


class EstimationError(Exception):
    """Base class for estimation errors. The message is safe to show to the end user."""


class PromptTemplateError(EstimationError):
    """A prompt version or template is missing: a server configuration error."""


class UnknownPromptVersionError(EstimationError):
    """The requested ``prompt_version`` does not match any folder under ``prompts/estimation/``."""


class LLMProviderError(EstimationError):
    """The LLM provider failed (network, timeout, rate limit, empty answer…)."""


class SessionNotFoundError(EstimationError):
    """The ``session_id`` is unknown: never created, or lost on a service restart."""


class InputRejectedError(EstimationError):
    """An input guardrail refused the description (prompt injection, moderation…).

    ``reason`` is a stable machine-readable tag for logs and tests; the message is user-facing.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason
