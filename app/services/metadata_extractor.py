"""Updates a session's ``ProjectMetadata`` after each estimate with a second, small LLM call.

Why an LLM extractor and not regex: fields such as the agreed scope are semantic (they merge what
the conversation added and removed), which a pattern cannot summarise. The cost is one extra call
per turn; it reuses ``LLMProvider.complete``, so the provider contract does not grow.

The extracted facts end up in the *system* prompt of later turns, and they come from user text:
that is a prompt-injection escalation path. So every string is checked with the same injection
heuristics as the input, values are length-capped, and the template marks the block as data.

Extraction never breaks a turn: on any failure (provider error, invalid JSON, schema mismatch)
the previous metadata is kept and a warning is logged.
"""

import json
import re

import structlog
from pydantic import ValidationError

from app.exceptions import LLMProviderError
from app.prompts.loader import render_metadata_prompt
from app.schemas.sessions import ProjectMetadata
from app.services.guardrails.input import prompt_injection_pattern
from app.services.llm.base import LLMProvider

logger = structlog.get_logger()

MAX_NAME_CHARS = 120
MAX_SCOPE_CHARS = 1_000
MAX_TECHNOLOGIES = 30
MAX_TECHNOLOGY_CHARS = 50

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class MetadataExtractor:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def update(
        self, known: ProjectMetadata, description: str, estimate: str, language: str = "es"
    ) -> ProjectMetadata:
        """The known facts merged with what this turn adds; ``known`` itself on any failure.

        ``language`` is the response language the facts are written in.
        """
        system, user = render_metadata_prompt(known, description, estimate, language)
        try:
            raw = self._provider.complete(system, user)
            extracted = ProjectMetadata.model_validate_json(_FENCE_RE.sub("", raw.strip()))
        except (LLMProviderError, ValidationError, json.JSONDecodeError) as exc:
            logger.warning("metadata_extraction_failed", error_type=type(exc).__name__)
            return known
        merged = merge_metadata(known, extracted)
        logger.info("metadata_updated", fields=sorted(_changed_fields(known, merged)))
        return merged


def merge_metadata(known: ProjectMetadata, extracted: ProjectMetadata) -> ProjectMetadata:
    """New non-empty, safe values replace old ones; technologies accumulate without duplicates."""
    technologies = list(known.mentioned_technologies)
    seen = {technology.casefold() for technology in technologies}
    for technology in extracted.mentioned_technologies:
        clean = _safe_text(technology, MAX_TECHNOLOGY_CHARS)
        if clean and clean.casefold() not in seen and len(technologies) < MAX_TECHNOLOGIES:
            technologies.append(clean)
            seen.add(clean.casefold())

    return ProjectMetadata(
        project_name=_safe_text(extracted.project_name, MAX_NAME_CHARS) or known.project_name,
        assumed_team_size=extracted.assumed_team_size or known.assumed_team_size,
        mentioned_technologies=technologies,
        agreed_scope=_safe_text(extracted.agreed_scope, MAX_SCOPE_CHARS) or known.agreed_scope,
    )


def _safe_text(value: str | None, max_chars: int) -> str | None:
    """Single-line, capped text, or ``None`` when empty or when it looks like an injection."""
    if value is None:
        return None
    text = " ".join(value.split())[:max_chars].strip()
    if not text:
        return None
    if prompt_injection_pattern(text) is not None:
        logger.warning("metadata_value_rejected", reason="prompt_injection")
        return None
    return text


def _changed_fields(before: ProjectMetadata, after: ProjectMetadata) -> set[str]:
    return {name for name in ProjectMetadata.model_fields if getattr(before, name) != getattr(after, name)}
