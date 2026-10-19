"""Stress metrics over a ``TurnObservation`` and a session snapshot.

They live apart from ``evals.metrics`` because their input differs: a
``TurnObservation`` (telemetry returned with every session turn) and the JSON of
``GET /api/v1/sessions/{id}``, not a ``(GoldenCase, Markdown answer)`` pair. The
``MetricResult`` dataclass is reused from ``evals.metrics`` so reports stay uniform.

All checks are deterministic: no embeddings, no LLM judge.
"""

from collections.abc import Iterable
from typing import Any, Literal

from app.schemas.sessions import TurnObservation
from evals.metrics import MetricResult

Where = Literal["summary", "anchors", "metadata"]
_ALL_WHERE: tuple[Where, ...] = ("summary", "anchors", "metadata")


class LatencyBudgetMetric:
    """Per-turn server-side latency under a wall-clock budget (``<=`` passes)."""

    name = "latency_budget"

    def __init__(self, budget_ms: int) -> None:
        if budget_ms <= 0:
            raise ValueError("budget_ms must be positive")
        self.budget_ms = budget_ms

    def evaluate(self, observation: TurnObservation) -> MetricResult:
        passed = observation.latency_ms <= self.budget_ms
        return MetricResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=f"{observation.latency_ms:g} ms vs budget {self.budget_ms} ms",
        )


class CostBudgetMetric:
    """Cost of a single turn under a USD budget (``<=`` passes); cumulative spend is the runner's job."""

    name = "cost_budget"

    def __init__(self, budget_usd: float) -> None:
        if budget_usd <= 0:
            raise ValueError("budget_usd must be positive")
        self.budget_usd = budget_usd

    def evaluate(self, observation: TurnObservation) -> MetricResult:
        passed = observation.cost_usd <= self.budget_usd
        return MetricResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=f"${observation.cost_usd:.6f} vs budget ${self.budget_usd:.6f}",
        )


class MemoryDriftMetric:
    """Does a fact introduced in an earlier turn still appear in the session memory?

    ``where`` selects the parts of the ``GET /sessions/{id}`` snapshot to search:

    - ``summary``  -- the running summary of folded turns.
    - ``anchors``  -- the verbatim anchored user messages.
    - ``metadata`` -- every ``project_metadata`` value, flattened to text.

    Matching is a case-insensitive substring. A missing field counts as empty.
    """

    name = "memory_drift"

    def __init__(self, fact: str, where: Iterable[Where] = _ALL_WHERE) -> None:
        if not fact:
            raise ValueError("fact must be a non-empty string")
        self.fact = fact
        self.where = tuple(where)
        unknown = set(self.where) - set(_ALL_WHERE)
        if unknown or not self.where:
            raise ValueError(f"where must be a non-empty subset of {_ALL_WHERE}, got {self.where}")

    def evaluate(self, snapshot: dict[str, Any]) -> MetricResult:
        needle = self.fact.lower()
        found_in = [part for part in self.where if needle in self._text(snapshot, part).lower()]
        passed = bool(found_in)
        return MetricResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=f"fact={self.fact!r} {'found in ' + ','.join(found_in) if passed else 'missing from ' + ','.join(self.where)}",
        )

    @staticmethod
    def _text(snapshot: dict[str, Any], part: Where) -> str:
        if part == "summary":
            return str(snapshot.get("summary") or "")
        if part == "anchors":
            return "\n".join(str(a) for a in snapshot.get("anchors") or [])
        return " ".join(_flatten(snapshot.get("project_metadata") or {}))


def _flatten(value: Any) -> list[str]:
    """Every scalar inside ``value`` as text (lists and dicts are walked, ``None`` skipped)."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [text for item in value.values() for text in _flatten(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _flatten(item)]
    return [str(value)]
