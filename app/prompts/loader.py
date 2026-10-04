"""Loads and renders the versioned Jinja2 estimation prompts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from app.exceptions import PromptTemplateError
from app.schemas.estimations import EstimationRequest
from app.schemas.sessions import ProjectMetadata

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
def _system_prompt(version: str, detail_level: str, output_format: str, language: str) -> str:
    # Never includes the description, so there are only a few variants per version. Rules and
    # examples come first and are identical for every request (the provider caches that prefix);
    # only the short trailing blocks (request.j2, language.j2) depend on these arguments.
    return _render(
        version,
        "system.j2",
        detail_level=detail_level,
        output_format=output_format,
        language=language,
    )


def render_estimation_examples(version: str = PROMPT_VERSION) -> str:
    """Return the few-shot examples block exactly as it is injected into the system prompt."""
    return _render(version, "examples.j2")


def _system_prompt_with_metadata(
    version: str, detail_level: str, output_format: str, language: str, metadata: ProjectMetadata
) -> str:
    # Not cached: the metadata changes on every session turn. It is the last block, so the
    # provider still caches the same static prefix as ``_system_prompt``.
    return _render(
        version,
        "system.j2",
        detail_level=detail_level,
        output_format=output_format,
        language=language,
        project_metadata=metadata,
    )


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = PROMPT_VERSION,
    project_metadata: ProjectMetadata | None = None,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts ready for the LLM.

    Templates live under ``app/prompts/estimation/<version>/``. The system prompt ends with the
    instructions for the requested detail level and output format, and with an instruction to
    answer entirely in ``request.language``. Session requests pass ``project_metadata``: the
    system prompt then closes with a ``<project_metadata>`` block (empty tags on the first turn).
    Versions whose ``system.j2`` predates the block ignore it.
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
    if project_metadata is None:
        return _system_prompt(*parameters), user
    return _system_prompt_with_metadata(*parameters, project_metadata), user


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
