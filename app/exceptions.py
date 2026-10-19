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


class AttachmentError(EstimationError):
    """An attachment cannot be used: unsupported type, too large, unreadable or without text."""


class InputRejectedError(EstimationError):
    """An input guardrail refused the description (prompt injection, moderation…).

    ``reason`` is a stable machine-readable tag for logs and tests; the message is user-facing.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class IngestionSourceNotFoundError(EstimationError):
    """The requested ingestion source is not declared in the data catalog."""

    def __init__(self, source_name: str) -> None:
        super().__init__(f"Source {source_name!r} not found in catalog")
        self.source_name = source_name
        self.reason = "unknown_source"


class IngestionSourceNotIncludedError(EstimationError):
    """The source exists but its catalog decision is not ``include`` (review / exclude)."""

    def __init__(self, source_name: str, *, decision: str, decision_reason: str | None) -> None:
        super().__init__(
            f"Source {source_name!r} has decision={decision!r}; only 'include' sources can be ingested"
        )
        self.source_name = source_name
        self.decision = decision
        self.decision_reason = decision_reason
        self.reason = "source_not_included"


class IngestionJobNotFoundError(EstimationError):
    """The ``job_id`` is unknown."""

    def __init__(self, job_id: object) -> None:
        super().__init__(f"Ingestion job {job_id} not found")
        self.job_id = job_id
        self.reason = "unknown_job"
