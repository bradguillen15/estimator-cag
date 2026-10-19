"""Unit tests for the stress metrics: deterministic, no network, no files."""

from typing import Any

import pytest

from app.schemas.sessions import TurnObservation
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import all_scenarios


def _obs(**overrides: Any) -> TurnObservation:
    base: dict[str, Any] = {
        "turn_index": 1,
        "session_id": "sess-test",
        "enriched_transcript_chars": 200,
        "attachments_total_chars": 0,
        "messages_in_window": 2,
        "anchors_count": 0,
        "summary_chars": 0,
        "tokens_in": 500,
        "tokens_out": 300,
        "cost_usd": 0.001,
        "latency_ms": 1500,
        "cache_hit_kind": "none",
    }
    return TurnObservation(**{**base, **overrides})


def _snapshot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "summary": "",
        "anchors": [],
        "project_metadata": {
            "project_name": None,
            "assumed_team_size": None,
            "mentioned_technologies": [],
            "agreed_scope": None,
        },
    }
    return {**base, **overrides}


def test_latency_pass_fail_and_boundary() -> None:
    metric = LatencyBudgetMetric(budget_ms=4000)
    assert metric.evaluate(_obs(latency_ms=3200)).passed is True
    assert metric.evaluate(_obs(latency_ms=4000)).passed is True  # == budget passes
    failed = metric.evaluate(_obs(latency_ms=4001))
    assert (failed.passed, failed.score) == (False, 0.0)


def test_cost_pass_fail_and_boundary() -> None:
    metric = CostBudgetMetric(budget_usd=0.005)
    assert metric.evaluate(_obs(cost_usd=0.0035)).passed is True
    assert metric.evaluate(_obs(cost_usd=0.005)).passed is True  # == budget passes
    assert metric.evaluate(_obs(cost_usd=0.01)).passed is False


@pytest.mark.parametrize("bad", [0, -1])
def test_budgets_must_be_positive(bad: float) -> None:
    with pytest.raises(ValueError):
        LatencyBudgetMetric(budget_ms=int(bad))
    with pytest.raises(ValueError):
        CostBudgetMetric(budget_usd=bad)


def test_drift_found_in_summary_case_insensitive() -> None:
    metric = MemoryDriftMetric("NIMBUS", where=("summary",))
    assert metric.evaluate(_snapshot(summary="Project nimbus kicked off.")).passed is True


def test_drift_found_in_anchors() -> None:
    metric = MemoryDriftMetric("signed NDA", where=("anchors",))
    assert metric.evaluate(_snapshot(anchors=["We signed NDA last week."])).passed is True


def test_drift_found_in_metadata_list_and_flattened_values() -> None:
    snap = _snapshot(
        project_metadata={"project_name": "Atlas", "mentioned_technologies": ["React", "Flutter"], "assumed_team_size": 3}
    )
    assert MemoryDriftMetric("flutter", where=("metadata",)).evaluate(snap).passed is True
    assert MemoryDriftMetric("Atlas", where=("metadata",)).evaluate(snap).passed is True
    assert MemoryDriftMetric("3", where=("metadata",)).evaluate(snap).passed is True


def test_drift_only_searches_the_requested_parts() -> None:
    snap = _snapshot(summary="budget 80000 confirmed")
    assert MemoryDriftMetric("80000", where=("anchors", "metadata")).evaluate(snap).passed is False
    assert MemoryDriftMetric("80000", where=("anchors", "summary")).evaluate(snap).passed is True


def test_drift_tolerates_missing_fields() -> None:
    result = MemoryDriftMetric("Nimbus").evaluate({})
    assert result.passed is False
    assert result.score == 0.0


def test_drift_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError):
        MemoryDriftMetric("")
    with pytest.raises(ValueError):
        MemoryDriftMetric("x", where=())
    with pytest.raises(ValueError):
        MemoryDriftMetric("x", where=("budget",))  # type: ignore[arg-type]


def test_every_scenario_has_at_least_20_turns_and_a_tracked_first_fact() -> None:
    for scenario in all_scenarios():
        assert len(scenario.turns) >= 20, scenario.name
        assert scenario.turns[0].fact_introduced, scenario.name
        assert all(len(t.transcript) >= 20 for t in scenario.turns), scenario.name
