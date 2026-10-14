"""Loads and renders the versioned Jinja2 estimation prompts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from app.exceptions import PromptTemplateError
from app.schemas.critic import CriticIssue
from app.schemas.estimations import Audience, EstimationRequest
from app.schemas.sessions import HistoryMemory, ProjectMetadata, TurnPair

_PROMPTS_ROOT = Path(__file__).resolve().parent

# Active prompt version: the folder under estimation/ that requests are rendered with.
PROMPT_VERSION = "v3"


@lru_cache
def available_prompt_versions() -> tuple[str, ...]:
    """Versions discovered from the folders under ``estimation/`` (computed once)."""
    return tuple(sorted(p.name for p in (_PROMPTS_ROOT / "estimation").iterdir() if p.is_dir()))


def _build_environment(version_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(version_dir),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


@lru_cache
def _environment(version: str) -> Environment:
    version_dir = _PROMPTS_ROOT / "estimation" / version
    if not version_dir.is_dir():
        raise PromptTemplateError(f"Unknown prompt version: {version!r}")
    return _build_environment(version_dir)


def _render(version: str, template: str, **context: object) -> str:
    try:
        return _environment(version).get_template(template).render(**context).strip()
    except TemplateNotFound as exc:
        raise PromptTemplateError(
            f"Missing template {exc.name!r} in estimation/{version}/"
        ) from exc


@lru_cache
def _system_prompt(
    version: str, detail_level: str, output_format: str, language: str, audience: str = ""
) -> str:
    # Never includes the description, so there are only a few variants per version. Rules and
    # examples come first and are identical for every request (the provider caches that prefix);
    # only the short trailing blocks (request.j2, language.j2, audience.j2) depend on these arguments.
    # ``audience`` is "" for the default tier: the variable is then not passed at all.
    return _render(
        version,
        "system.j2",
        detail_level=detail_level,
        output_format=output_format,
        language=language,
        **({"audience": audience} if audience else {}),
    )


def render_estimation_examples(version: str = PROMPT_VERSION) -> str:
    """Return the few-shot examples block exactly as it is injected into the system prompt."""
    return _render(version, "examples.j2")


def _system_prompt_with_metadata(
    version: str,
    detail_level: str,
    output_format: str,
    language: str,
    metadata: ProjectMetadata,
    history_memory: HistoryMemory | None = None,
    audience: str = "",
    critic_feedback: Sequence[CriticIssue] | None = None,
) -> str:
    # Not cached: the metadata changes on every session turn. The trailing blocks come last, so the
    # provider still caches the same static prefix as ``_system_prompt``. An empty memory is not
    # passed at all, which keeps the output identical to a prompt that never heard of it.
    context: dict[str, object] = {}
    if history_memory is not None and not history_memory.is_empty():
        context["history_memory"] = _neutralize(history_memory)
    if audience:
        context["audience"] = audience
    if critic_feedback:
        context["critic_feedback"] = _clean_feedback(critic_feedback)
    return _render(
        version,
        "system.j2",
        detail_level=detail_level,
        output_format=output_format,
        language=language,
        project_metadata=metadata,
        **context,
    )


_MEMORY_TAG_RE = re.compile(r"<(/?)\s*(conversation_summary|conversation_commitments|commitment|user|assistant)\b", re.IGNORECASE)


def _neutralize(memory: HistoryMemory) -> HistoryMemory:
    """Defuses text that would close the memory tags early (the content comes from user text)."""

    def clean(text: str) -> str:
        return _MEMORY_TAG_RE.sub(r"<\1 \2", text)

    return HistoryMemory(
        summary=clean(memory.summary),
        anchors=[TurnPair(user=clean(a.user), assistant=clean(a.assistant)) for a in memory.anchors],
    )


_CRITIC_TAG_RE = re.compile(r"<(/?)\s*(project_description|estimate_under_review)\b", re.IGNORECASE)
_FEEDBACK_TAG_RE = re.compile(r"<(/?)\s*(critic_feedback|issue)\b", re.IGNORECASE)


def _clean_feedback(issues: Sequence[CriticIssue]) -> list[CriticIssue]:
    # Messages come from an LLM that read user text, so tags that would close the block are defused.
    return [issue.model_copy(update={"message": _FEEDBACK_TAG_RE.sub(r"<\1 \2", issue.message)}) for issue in issues]


def _system_prompt_with_feedback(
    version: str,
    detail_level: str,
    output_format: str,
    language: str,
    issues: Sequence[CriticIssue],
    audience: str = "",
) -> str:
    # Not cached: the issues differ on every re-attempt. The block is trailing (prefix unchanged).
    cleaned = _clean_feedback(issues)
    return _render(
        version,
        "system.j2",
        detail_level=detail_level,
        output_format=output_format,
        language=language,
        critic_feedback=cleaned,
        **({"audience": audience} if audience else {}),
    )


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = PROMPT_VERSION,
    project_metadata: ProjectMetadata | None = None,
    history_memory: HistoryMemory | None = None,
    critic_feedback: Sequence[CriticIssue] | None = None,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts ready for the LLM.

    Templates live under ``app/prompts/estimation/<version>/``. The system prompt ends with the
    instructions for the requested detail level and output format, and with an instruction to
    answer entirely in ``request.language``. Session requests pass ``project_metadata``: the
    system prompt then closes with a ``<project_metadata>`` block (empty tags on the first turn).
    ``history_memory`` (summary + anchors of the turns that left the window) adds one more trailing
    block, only when non-empty and only together with ``project_metadata``. ``critic_feedback``
    (the Critic's issues, critic-review re-attempts, stateless or session) adds a last trailing
    block, only when non-empty. ``request.audience`` (the resolved tier;
    see ``services/audience.py``) adds an ``audience`` block after the language one, unless it is
    ``default`` or unset. Versions whose ``system.j2`` predates a
    block ignore it.
    """
    user = _render(
        version,
        "user.j2",
        description=request.description.strip(),
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
    )
    parameters = (version, request.detail_level.value, request.output_format.value, request.language.value)
    # The default tier adds no block, so its prompt stays identical to one that never heard of tiers.
    audience = request.audience.value if request.audience not in (None, Audience.DEFAULT) else ""
    if project_metadata is None:
        if critic_feedback:
            return _system_prompt_with_feedback(*parameters, critic_feedback, audience), user
        return _system_prompt(*parameters, audience), user
    return (
        _system_prompt_with_metadata(*parameters, project_metadata, history_memory, audience, critic_feedback),
        user,
    )


# Version of the project-metadata extraction prompt (app/prompts/metadata/<version>/).
METADATA_PROMPT_VERSION = "v2"  # v2: facts written in the response language


@lru_cache
def _metadata_environment(version: str) -> Environment:
    version_dir = _PROMPTS_ROOT / "metadata" / version
    if not version_dir.is_dir():
        raise PromptTemplateError(f"Unknown metadata prompt version: {version!r}")
    return _build_environment(version_dir)


def render_metadata_prompt(
    known: ProjectMetadata,
    description: str,
    estimate: str,
    language: str = "es",
    version: str = METADATA_PROMPT_VERSION,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for the LLM that extracts ``ProjectMetadata`` as JSON.

    ``language`` is the conversation's response language: the free-text facts are written in it,
    so the project memory reads in the same language as the estimates.
    """
    environment = _metadata_environment(version)
    system = environment.get_template("system.j2").render(language=language).strip()
    user = (
        environment.get_template("user.j2")
        .render(known_facts=known.model_dump_json(), description=description.strip(), estimate=estimate.strip())
        .strip()
    )
    return system, user


# Version of the history-summary prompt (app/prompts/summary/<version>/).
SUMMARY_PROMPT_VERSION = "v1"
_MAX_SUMMARY_TURN_CHARS = 4_000  # per message handed to the summarizer


@lru_cache
def _summary_environment(version: str) -> Environment:
    version_dir = _PROMPTS_ROOT / "summary" / version
    if not version_dir.is_dir():
        raise PromptTemplateError(f"Unknown summary prompt version: {version!r}")
    return _build_environment(version_dir)


def render_summary_prompt(
    previous_summary: str,
    turns: Sequence[TurnPair],
    language: str = "es",
    max_chars: int = 2_000,
    version: str = SUMMARY_PROMPT_VERSION,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for the LLM that folds evicted turns into the running summary."""
    environment = _summary_environment(version)
    system = environment.get_template("system.j2").render(language=language, max_chars=max_chars).strip()
    clipped = [
        TurnPair(user=t.user[:_MAX_SUMMARY_TURN_CHARS], assistant=t.assistant[:_MAX_SUMMARY_TURN_CHARS])
        for t in turns
    ]
    user = environment.get_template("user.j2").render(previous_summary=previous_summary, turns=clipped).strip()
    return system, user


# Version of the Critic prompt (app/prompts/critic/<version>/).
CRITIC_PROMPT_VERSION = "v1"


@lru_cache
def _critic_environment(version: str) -> Environment:
    version_dir = _PROMPTS_ROOT / "critic" / version
    if not version_dir.is_dir():
        raise PromptTemplateError(f"Unknown critic prompt version: {version!r}")
    return _build_environment(version_dir)


def render_critic_prompt(
    description: str, estimate: str, version: str = CRITIC_PROMPT_VERSION
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts for the LLM that audits an estimate and answers with JSON."""
    environment = _critic_environment(version)
    system = environment.get_template("system.j2").render().strip()
    # Both texts come from users / an LLM: defuse tags that would close the template's blocks early.
    user = (
        environment.get_template("user.j2")
        .render(
            description=_CRITIC_TAG_RE.sub(r"<\1 \2", description.strip()),
            estimate=_CRITIC_TAG_RE.sub(r"<\1 \2", estimate.strip()),
        )
        .strip()
    )
    return system, user
