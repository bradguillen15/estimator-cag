"""Decides what survives when turns leave the history window.

A turn whose user message carries a durable commitment (NDA, signed contract, frozen scope, locked
budget, compliance regime, hard deadline, explicit agreement) is an *anchor*: kept verbatim, because
a summary could soften it. Every other turn is folded into the running summary.

Detection is a deterministic regex over English and Spanish phrases. It is deliberately
conservative: a miss only demotes a turn to the summary, while a false positive bloats the prompt
because anchors are replayed on every turn (capped by ``SESSION_MAX_ANCHORS``).

Compression runs outside ``ConversationHistory`` so the window stays pure and testable.
"""

import re
from collections.abc import Sequence

import structlog

from app.schemas.sessions import TurnPair
from app.services.sessions import ConversationHistory
from app.services.summarizer import ConversationSummarizer

logger = structlog.get_logger()

_FLAGS = re.IGNORECASE
_ANCHOR_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("nda", re.compile(r"\b(nda|non[- ]?disclosure|under embargo|legal hold|confidencialidad|acuerdo de confidencialidad)\b", _FLAGS)),
    (
        "signed_contract",
        re.compile(
            r"\b(signed|countersigned)\s+(the\s+|a\s+)?(contract|sow|msa|agreement)\b"
            r"|\b(contrato|acuerdo|sow|msa)\s+(ya\s+)?(est[aá]\s+)?firmad[oa]\b"
            r"|\b(firmamos|hemos firmado|firmado)\s+(el\s+|un\s+)?(contrato|acuerdo)\b",
            _FLAGS,
        ),
    ),
    (
        "scope_frozen",
        re.compile(
            r"\b(scope|backlog)\s+(is\s+)?(frozen|locked|final|fixed)\b"
            r"|\b(alcance|backlog)\s+(est[aá]\s+|queda\s+|ya\s+est[aá]\s+)?(congelad[oa]|cerrad[oa]|fij[oa]|bloquead[oa]|definitiv[oa])\b",
            _FLAGS,
        ),
    ),
    (
        "budget_locked",
        re.compile(
            r"\b(budget|cap|ceiling)\s+(is\s+)?(locked|fixed|approved|capped)\b"
            r"|\bpresupuesto\s+(est[aá]\s+|ya\s+est[aá]\s+)?(aprobad[oa]|cerrad[oa]|fij[oa]|bloquead[oa]|limitad[oa])\b"
            r"|\bpresupuesto\s+(m[aá]ximo|tope)\b",
            _FLAGS,
        ),
    ),
    ("compliance", re.compile(r"\b(hipaa|gdpr|rgpd|lopd|sox|pci[- ]?dss|fda|iso[- ]?27001|regulator(?:y|io)|regulaci[oó]n|normativa)\b", _FLAGS)),
    (
        "deadline_hard",
        re.compile(
            r"\bhard\s+deadline\b|\bmust\s+go\s+live\s+by\b"
            r"|\bfecha\s+l[ií]mite\s+(innegociable|firme|fija)\b|\bdeadline\s+(innegociable|firme|fijo)\b|\bdebe\s+salir\s+(en\s+producci[oó]n\s+)?(antes|para)\b",
            _FLAGS,
        ),
    ),
    (
        "contractual",
        re.compile(
            r"\bcontractually\s+(bound|required|obliged|obligated)\b"
            r"|\b(obligad[oa]|obligaci[oó]n)\s+contractual(mente)?\b|\bcontractualmente\b",
            _FLAGS,
        ),
    ),
    (
        "explicit_commitment",
        re.compile(
            r"\b(we|the\s+(client|customer))\s+(agreed|committed)\s+to\b"
            r"|\b(nos\s+)?(comprometimos|acordamos)\s+(a|con)\b|\bel\s+cliente\s+(acord[oó]|se\s+comprometi[oó])\b",
            _FLAGS,
        ),
    ),
)


def anchor_rules(text: str) -> list[str]:
    """Names of the anchor rules that match ``text`` (empty when it is not an anchor)."""
    return [name for name, pattern in _ANCHOR_RULES if pattern.search(text)]


def is_anchor(text: str) -> bool:
    return bool(anchor_rules(text))


class HistoryCompressor:
    def __init__(self, summarizer: ConversationSummarizer) -> None:
        self._summarizer = summarizer

    def compress(self, history: ConversationHistory, evicted: Sequence[TurnPair], language: str = "es") -> None:
        """Keeps anchors verbatim in ``history`` and folds the rest into ``history.summary``."""
        if not evicted:
            return
        to_fold: list[TurnPair] = []
        rules: list[str] = []
        for pair in evicted:
            matched = anchor_rules(pair.user)
            if matched:
                history.add_anchor(pair)
                rules.extend(matched)
            else:
                to_fold.append(pair)
        if to_fold:
            history.summary = self._summarizer.summarize(history.summary, to_fold, language)
        logger.info(
            "history_compressed",
            anchored=len(evicted) - len(to_fold),
            folded=len(to_fold),
            anchor_rules=rules,
            anchors_count=len(history.anchors),
            summary_chars=len(history.summary),
        )
