"""Input guardrails: run on the description before anything else (cache, prompt, LLM).

1. Prompt-injection heuristics (English + Spanish): reject.
2. PII redaction (emails, phones, IBANs): replace with placeholders, never reject.
3. Moderation (optional, behind ``ModerationProvider``): reject flagged content; fails open.

The heuristics are deliberately conservative: a false positive blocks a legitimate client, and the
prompt already has its own defence. They are a cheap first line, not a compliance-grade filter.
Text is NFKC-normalized and stripped of zero-width characters before the injection match, but
obfuscation such as leetspeak ("1gn0re") or other languages is out of scope (best effort).

Injection patterns anchor on addressing the assistant ("ignore the previous instructions", "you are
now a/an/the ...") rather than on single words, so requirements like "the system must ignore
duplicated validation rules" or "you are now able to filter orders" are not rejected.
"""

import re
import unicodedata
from collections.abc import Callable

import structlog

from app.exceptions import InputRejectedError
from app.services.llm.base import ModerationProvider

logger = structlog.get_logger()

_INJECTION_MESSAGE = (
    "La descripción contiene instrucciones dirigidas al asistente en lugar de describir el proyecto. "
    "Reescríbela explicando solo qué quieres construir."
)
_MODERATION_MESSAGE = (
    "La descripción contiene contenido que no podemos procesar. "
    "Revísala y vuelve a intentarlo describiendo solo el proyecto."
)

_FLAGS = re.IGNORECASE
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200d\ufeff\u2060]")
_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, _FLAGS)
    for pattern in (
        # English. The object noun must directly follow the qualifier: "ignore previous rules and
        # instructions cached in the old system" is a requirement, not an attack (documented choice).
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|every\s+)?(?:of\s+)?"
        r"(?:the\s+|your\s+|these\s+|those\s+)?(?:previous|prior|above|earlier|preceding|system|initial|original|all)\s+"
        r"(?:instructions?|prompts?)\b",
        r"\b(?:ignore|disregard|forget|override)\s+(?:the\s+above|your(?:\s+previous)?)\s+(?:rules|guidelines)\b",
        r"\b(?:ignore|disregard|forget)\s+(?:everything|all)\s+(?:above|before|that\s+came\s+before)\b",
        r"\bforget\s+everything\s+(?:you|i|we)\s+(?:were|was|have|had|said|told|know)\b",
        r"\byou\s+are\s+now\s+(?:a|an|the|dan)\b",
        r"\bnew\s+instructions?\s*[:.\-]",
        r"\b(?:reveal|show|print|repeat|display)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)\b",
        r"\bjailbreak\b",
        # Spanish (tú and voseo). Imperative forms only: "ignorar las reglas..." is a requirement.
        r"\b(?:ignora|ignorá|ignore|olvida|olvidá|olvide)\s+(?:todas?\s+)?(?:(?:las|tus|sus|esas|estas|los)\s+)?"
        r"(?:instrucciones|indicaciones|pautas|directrices)\b",
        r"\b(?:ignora|ignorá)\s+(?:las\s+reglas\s+(?:anteriores|previas)|tus\s+reglas)\b",
        r"\b(?:ignora|ignorá)\s+(?:por\s+completo\s+)?todo\s+lo\s+anterior\b",
        r"\bolvid[aá]\s+(?:todo\s+lo\s+(?:anterior|que\s+te)|lo\s+anterior)\b",
        r"\b(?:ahora|a\s+partir\s+de\s+ahora)\s+(?:eres|sos)\s+(?:un|una|el|la|mi)\b",
        r"\bnuev[ao]s?\s+(?:instrucci[oó]n(?:es)?|reglas?)\s*[:.\-]",
        r"\b(?:revela|muestra|muéstrame|imprime|repite)\s+(?:tu|el|tus|las)\s+(?:system\s+)?(?:prompt|instrucciones)\b",
        # Structural tags that try to close the description block or open a new role.
        r"</?\s*(?:system|instructions?|prompt|assistant|project_description)\s*>",
    )
)


def _normalize_for_injection(text: str) -> str:
    return _ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFKC", text))


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Country code + check digits + 12-30 alphanumerics, optionally grouped in blocks of four.
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
# Phone shapes (a bare digit run is not enough: IDs, versions and hour lists look alike):
_PHONE_PAREN_RE = re.compile(r"(?<![\w.,/])\(\+?\d{2,4}\)[ .\-]?\d[\d .\-]{4,14}\d")
_PHONE_PLUS_RE = re.compile(r"(?<![\w.,/])\+\d[\d ().\-]{6,18}\d")
# 2-4 digit groups joined by one consistent separator.
_PHONE_GROUPED_RE = re.compile(r"(?<![\w.,/-])\d{2,4}([ .\-])\d{2,4}(?:\1\d{2,4}){1,4}(?![\w]|[.\-]\d)")
_PHONE_PLAIN_RE = re.compile(r"(?<![\w.,/+-])\d{9,10}(?![\w]|[.\-]\d)")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CURRENCY_BEFORE_RE = re.compile(r"[€$£]\s*$")
_CURRENCY_AFTER_RE = re.compile(r"^\s*(?:[€$£]|eur\b|euros?\b|usd\b|d[oó]lares\b|mxn\b|cop\b|ars\b)", re.IGNORECASE)
_DOTTED_AMOUNT_RE = re.compile(r"^\d{1,3}(?:\.\d{3}){2,}$")
_ZERO_TAIL_RE = re.compile(r"(?:[ .\-]000)+$")


def _digits_in_range(candidate: str, low: int, high: int) -> bool:
    return low <= len(re.sub(r"\D", "", candidate)) <= high


def _is_money_or_date(candidate: str, before: str, after: str) -> bool:
    # Money is not a phone number: "1.500.000.000", "150 000 000 €", "$ 600 000 000".
    return bool(
        _ISO_DATE_RE.search(candidate)
        or _DOTTED_AMOUNT_RE.match(candidate)
        or _ZERO_TAIL_RE.search(candidate)
        or _CURRENCY_BEFORE_RE.search(before)
        or _CURRENCY_AFTER_RE.match(after)
    )


def _is_grouped_phone(candidate: str) -> bool:
    groups = re.split(r"[ .\-]", candidate)
    # "612 34 56 78" / "600 123 456" / "11 5555 1234" are phones; "40 60 80 100" is a list of hours.
    return _digits_in_range(candidate, 9, 15) and (len(groups[0]) >= 3 or _digits_in_range(candidate, 10, 15))


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Replaces emails, IBANs and phone numbers with placeholders; returns the text and counts."""
    counts = {"email": 0, "iban": 0, "phone": 0}

    def _sub(kind: str, placeholder: str, pattern: re.Pattern[str], value: str) -> str:
        redacted, n = pattern.subn(placeholder, value)
        counts[kind] += n
        return redacted

    text = _sub("email", "[EMAIL]", _EMAIL_RE, text)
    text = _sub("iban", "[IBAN]", _IBAN_RE, text)

    def _phones(pattern: re.Pattern[str], value: str, accept: Callable[[str], bool]) -> str:
        def _replace(match: re.Match[str]) -> str:
            candidate = match.group(0)
            before, after = value[max(0, match.start() - 4) : match.start()], value[match.end() : match.end() + 12]
            if accept(candidate) and not _is_money_or_date(candidate, before, after):
                counts["phone"] += 1
                return "[PHONE]"
            return candidate

        return pattern.sub(_replace, value)

    text = _phones(_PHONE_PAREN_RE, text, lambda c: _digits_in_range(c, 9, 15))
    text = _phones(_PHONE_PLUS_RE, text, lambda c: _digits_in_range(c, 8, 15))
    text = _phones(_PHONE_GROUPED_RE, text, _is_grouped_phone)
    text = _phones(_PHONE_PLAIN_RE, text, lambda _c: True)
    return text, {kind: n for kind, n in counts.items() if n}


def prompt_injection_pattern(text: str) -> int | None:
    """Index of the first injection pattern that matches ``text``, or ``None`` if it looks clean."""
    normalized = _normalize_for_injection(text)
    for index, pattern in enumerate(_PROMPT_INJECTION_PATTERNS):
        if pattern.search(normalized):
            return index
    return None


class InputGuardrails:
    """Validates and sanitizes a description. ``check`` returns the text the LLM may see."""

    def __init__(self, moderator: ModerationProvider | None = None) -> None:
        self._moderator = moderator

    def check(self, description: str) -> str:
        self._reject_prompt_injection(description)
        sanitized, redactions = redact_pii(description)
        if redactions:
            logger.info("pii_redacted", **redactions)
        self._moderate(sanitized)
        return sanitized

    @staticmethod
    def _reject_prompt_injection(description: str) -> None:
        index = prompt_injection_pattern(description)
        if index is not None:
            logger.warning("input_rejected", reason="prompt_injection", pattern_index=index)
            raise InputRejectedError(_INJECTION_MESSAGE, reason="prompt_injection")

    def _moderate(self, text: str) -> None:
        if self._moderator is None:
            return
        try:
            categories = self._moderator.flagged_categories(text)
        except Exception as exc:
            # Fail open: a moderation outage must not take the estimator down.
            logger.warning("moderation_failed_open", error_type=type(exc).__name__)
            return
        if categories:
            logger.warning("input_rejected", reason="moderation", categories=categories)
            raise InputRejectedError(_MODERATION_MESSAGE, reason="moderation")
