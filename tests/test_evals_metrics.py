"""Metrics and dataset validation (no LLM involved)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.dataset import GoldenCase, load_dataset
from evals.metrics import (
    ContentRecallMetric,
    CostBoundsMetric,
    SchemaAdherenceMetric,
    parse_total_hours,
    run_all_metrics,
)


def _case(**overrides: object) -> GoldenCase:
    data: dict[str, object] = {
        "id": "c1",
        "description": "Portal interno para reservar salas con calendario.",
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "line_items",
        "language": "es",
        "min_hours": 100,
        "max_hours": 300,
        "expected_keywords": ["calendario", "email"],
    }
    data.update(overrides)
    return GoldenCase.model_validate(data)


ES_ANSWER = "## Estimación: Salas\n\nCalendario y avisos por e-mail.\n\n**Total estimado: 200 horas**"


def test_golden_dataset_is_valid_and_diverse() -> None:
    cases = load_dataset()
    assert len(cases) >= 6
    assert {c.language.value for c in cases} == {"es", "en"}
    assert len({c.detail_level for c in cases}) == 3
    assert len({c.output_format for c in cases}) == 3
    assert any(c.insufficient_information for c in cases)


def test_dataset_rejects_inverted_bounds_and_duplicates(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        _case(min_hours=500, max_hours=100)
    with pytest.raises(ValidationError):
        _case(min_hours=None)
    with pytest.raises(ValidationError):
        _case(insufficient_information=True)  # bounds not allowed there
    dup = tmp_path / "d.json"
    dup.write_text(json.dumps([_case().model_dump(mode="json")] * 2), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(dup)
    empty = tmp_path / "e.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="no cases"):
        load_dataset(empty)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**Total estimado: 120 horas**", 120),
        ("**Total estimate: 1,200 hours**", 1200),
        ("Total estimado: 1.200 horas", 1200),
        ("**Total estimate:** 85.5 hours", 85.5),
        ("no total here", None),
        ("Total estimado: horas", None),
    ],
)
def test_parse_total_hours(text: str, expected: float | None) -> None:
    assert parse_total_hours(text) == expected


def test_schema_adherence_pass_and_fail() -> None:
    metric = SchemaAdherenceMetric()
    assert metric.evaluate(_case(), ES_ANSWER).passed
    failed = metric.evaluate(_case(), "I cannot help with that.")
    assert not failed.passed and failed.score == 0.0


def test_cost_bounds_within_outside_and_unparseable() -> None:
    metric = CostBoundsMetric()
    assert metric.evaluate(_case(), ES_ANSWER).passed
    assert not metric.evaluate(_case(max_hours=150), ES_ANSWER).passed
    unparseable = metric.evaluate(_case(), "## Estimación\n\nsin total")
    assert not unparseable.passed and "parse" in unparseable.details


def test_cost_bounds_insufficient_information_case() -> None:
    case = _case(language="en", insufficient_information=True, min_hours=None, max_hours=None)
    metric = CostBoundsMetric()
    assert metric.evaluate(case, "## Insufficient information\n\nWhat is the scope?").passed
    assert not metric.evaluate(case, "**Total estimate: 50 hours**").passed
    assert not metric.evaluate(case, "random text").passed


def test_content_recall_is_case_and_accent_insensitive() -> None:
    metric = ContentRecallMetric()
    full = metric.evaluate(_case(expected_keywords=["CALENDARIO", "estimación"]), ES_ANSWER)
    assert full.score == 1.0 and full.passed
    half = metric.evaluate(_case(), ES_ANSWER.replace("e-mail", "aviso"))
    assert half.score == 0.5 and not half.passed and "email" in half.details
    assert metric.evaluate(_case(expected_keywords=[]), ES_ANSWER).passed


def test_run_all_metrics_returns_one_result_per_metric() -> None:
    results = run_all_metrics(_case(expected_keywords=["calendario"]), ES_ANSWER)
    assert [r.name for r in results] == ["schema_adherence", "cost_bounds", "content_recall"]
    assert all(r.passed for r in results)
