"""Deterministic metrics over a ``(GoldenCase, Markdown answer)`` pair. No LLM judge."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.services.guardrails.output import check_estimation_output
from evals.dataset import GoldenCase

RECALL_PASS_THRESHOLD = 0.6

# Matches the closing-block total in either response language: "Total estimado: 120 horas".
_TOTAL_RE = re.compile(r"total\s+estimad[oa]\s*:?\**\s*:?\s*\**\s*(\d[\d.,]*)|total\s+estimate\s*:?\**\s*:?\s*\**\s*(\d[\d.,]*)", re.IGNORECASE)
_THOUSANDS_RE = re.compile(r"^\d{1,3}([.,]\d{3})+$")
_INSUFFICIENT_RE = re.compile(r"^[ \t]*#{1,6}[ \t]*(Insufficient information|Información insuficiente)", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: str


class Metric(Protocol):
    name: str

    def evaluate(self, case: GoldenCase, text: str) -> MetricResult: ...


def parse_total_hours(text: str) -> float | None:
    """The first number after the "Total estimate/estimado" label, or ``None`` if absent or unreadable."""
    match = _TOTAL_RE.search(text)
    if match is None:
        return None
    raw = (match.group(1) or match.group(2)).rstrip(".,")
    if _THOUSANDS_RE.match(raw):
        raw = re.sub(r"[.,]", "", raw)
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _result(name: str, passed: bool, details: str, score: float | None = None) -> MetricResult:
    return MetricResult(name=name, score=score if score is not None else (1.0 if passed else 0.0), passed=passed, details=details)


class SchemaAdherenceMetric:
    """The answer follows the mandatory structure (same check as the production output guardrail)."""

    name = "schema_adherence"

    def evaluate(self, case: GoldenCase, text: str) -> MetricResult:
        check = check_estimation_output(text, case.language)
        return _result(self.name, check.passed, "schema ok" if check.passed else (check.reason or "failed"))


class CostBoundsMetric:
    """Total hours fall inside the case bounds; an insufficient-information case expects the heading and no total."""

    name = "cost_bounds"

    def evaluate(self, case: GoldenCase, text: str) -> MetricResult:
        total = parse_total_hours(text)
        if case.insufficient_information:
            asked = _INSUFFICIENT_RE.search(text) is not None
            if asked and total is None:
                return _result(self.name, True, "asked for more information")
            return _result(self.name, False, "expected the insufficient-information reply without a total")
        if total is None:
            return _result(self.name, False, "could not parse the total hours")
        assert case.min_hours is not None and case.max_hours is not None  # guaranteed by GoldenCase validation
        if case.min_hours <= total <= case.max_hours:
            return _result(self.name, True, f"{total:g}h within [{case.min_hours:g}, {case.max_hours:g}]")
        return _result(self.name, False, f"{total:g}h outside [{case.min_hours:g}, {case.max_hours:g}]")


class ContentRecallMetric:
    """Fraction of expected keywords present (case- and accent-insensitive)."""

    name = "content_recall"

    def evaluate(self, case: GoldenCase, text: str) -> MetricResult:
        if not case.expected_keywords:
            return _result(self.name, True, "no expected keywords")
        haystack = _normalize(text)
        missing = [kw for kw in case.expected_keywords if _normalize(kw) not in haystack]
        score = 1 - len(missing) / len(case.expected_keywords)
        details = "all keywords present" if not missing else f"missing: {', '.join(missing)}"
        return _result(self.name, score >= RECALL_PASS_THRESHOLD, details, score)


DEFAULT_METRICS: tuple[Metric, ...] = (SchemaAdherenceMetric(), CostBoundsMetric(), ContentRecallMetric())


def run_all_metrics(case: GoldenCase, text: str, metrics: tuple[Metric, ...] = DEFAULT_METRICS) -> list[MetricResult]:
    return [metric.evaluate(case, text) for metric in metrics]
