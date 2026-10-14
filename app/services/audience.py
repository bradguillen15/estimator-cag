"""Audience tier: who will read the estimate, inferred without an LLM.

The tier only changes the framing of the answer (a trailing ``audience`` prompt block), never the
estimation rules. Pure regexes over the guardrail-processed text, so it is free, deterministic and
explainable: the resolver returns the tier *and* the name of the rule that chose it.

Precedence (first match wins):

1. ``explicit_override``  the caller sent ``audience`` -> that value, always.
2. ``compliance_terms``   NDA, confidentiality, regulatory (GDPR, HIPAA...), board or investor
                          -> executive (these readers want risks and ranges, not detail).
3. ``executive_terms``    C-level / sponsor vocabulary (CEO, ROI, business case...) -> executive.
4. ``technical_audience`` two or more distinct developer keywords -> developer.
5. ``small_team``         session metadata says the team is 2 people or fewer -> developer.
6. ``pm_signals``         delivery vocabulary (sprint, roadmap, stakeholders...) -> pm.
7. ``default``            nothing matched -> default (no extra prompt block).

A single developer keyword is deliberately not enough: "we run on docker" is too weak a signal.
"""

import re
from dataclasses import dataclass

import structlog

from app.schemas.estimations import Audience
from app.schemas.sessions import ProjectMetadata

log = structlog.get_logger()

__all__ = ["AudienceResolution", "resolve_audience"]

_FLAGS = re.IGNORECASE

_COMPLIANCE = re.compile(
    r"\b(nda|non[- ]?disclosure|confidential(?:ity)?|confidencial(?:idad)?|"
    r"acuerdo de confidencialidad|under embargo|legal hold|"
    r"hipaa|gdpr|rgpd|sox|pci[- ]?dss|fda|iso[- ]?27001|ccpa|"
    r"regulator[iy]|regulatory|regulatorio|regulaci[oó]n|"
    r"board|investors?|inversores|inversionistas|junta directiva|consejo de administraci[oó]n)\b",
    _FLAGS,
)
_EXECUTIVE = re.compile(
    r"\b(ceo|cfo|cto|c-level|executive summary|resumen ejecutivo|sponsor|patrocinador|"
    r"roi|business case|caso de negocio|direcci[oó]n general|ejecutivos?)\b",
    _FLAGS,
)
_DEVELOPER = re.compile(
    r"\b(api|apis|rest|graphql|grpc|database|base de datos|microservices?|microservicios?|"
    r"ci\s*/\s*cd|docker|kubernetes|k8s|terraform|schema|esquema|endpoints?|backend|frontend|"
    r"repository|repositorio|refactor(?:ing)?|webhooks?|oauth|sdk|kafka|rabbitmq|airflow|"
    r"unit tests?|pruebas unitarias|migraci[oó]n de datos|data migration)\b",
    _FLAGS,
)
_PM = re.compile(
    r"\b(sprints?|roadmap|hoja de ruta|stakeholders?|interesados|milestones?|hitos?|backlog|"
    r"deliverables?|entregables?|gantt|kick-?off|dependencies|dependencias|velocity|velocidad del equipo)\b",
    _FLAGS,
)

_MIN_DEVELOPER_KEYWORDS = 2
_SMALL_TEAM = 2


@dataclass(frozen=True)
class AudienceResolution:
    audience: Audience
    rule: str


def _distinct(pattern: re.Pattern[str], text: str) -> int:
    return len({match.lower() for match in pattern.findall(text)})


def resolve_audience(
    text: str,
    explicit: Audience | None = None,
    metadata: ProjectMetadata | None = None,
) -> AudienceResolution:
    """Return the tier for ``text`` (the sanitized description) and the rule that chose it.

    ``metadata`` is the session's project memory; stateless requests pass ``None``.
    """
    if explicit is not None:
        result = AudienceResolution(explicit, "explicit_override")
    elif _COMPLIANCE.search(text) or (metadata and metadata.agreed_scope and _COMPLIANCE.search(metadata.agreed_scope)):
        result = AudienceResolution(Audience.EXECUTIVE, "compliance_terms")
    elif _EXECUTIVE.search(text):
        result = AudienceResolution(Audience.EXECUTIVE, "executive_terms")
    elif _distinct(_DEVELOPER, text) >= _MIN_DEVELOPER_KEYWORDS:
        result = AudienceResolution(Audience.DEVELOPER, "technical_audience")
    elif metadata and metadata.assumed_team_size is not None and metadata.assumed_team_size <= _SMALL_TEAM:
        result = AudienceResolution(Audience.DEVELOPER, "small_team")
    elif _PM.search(text):
        result = AudienceResolution(Audience.PM, "pm_signals")
    else:
        result = AudienceResolution(Audience.DEFAULT, "default")
    log.info("audience_resolved", audience=result.audience.value, rule=result.rule)
    return result
