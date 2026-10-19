"""Smoke tests of the stress runner against the in-process API with a fake LLM (never billed)."""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evals.stress.fixtures.build_pdfs import build_all, extracted_chars, pdf_path
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric
from evals.stress.run import CSV_COLUMNS, RunConfig, run_stress
from evals.stress.scenarios import get_scenario


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(LatencyBudgetMetric(60_000), CostBudgetMetric(10.0), fixtures_dir=tmp_path / "fixtures")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def test_runner_writes_csv_with_expected_columns_and_rows(client: TestClient, tmp_path: Path) -> None:
    out = tmp_path / "smoke.csv"
    total = run_stress(client, [get_scenario("growing")], [0, 5], 1, _config(tmp_path), out, max_turns=2)

    assert total == 4  # 1 scenario x 2 sizes x 1 repeat x 2 turns
    with out.open() as fh:
        assert csv.DictReader(fh).fieldnames == CSV_COLUMNS
    rows = _read(out)
    assert len(rows) == 4
    assert {r["attachment_size_kb"] for r in rows} == {"0", "5"}
    for row in rows:
        assert row["scenario"] == "growing"
        assert row["tracked_fact"] == "Nimbus"
        assert row["status_code"] == "200"
        assert row["error"] == ""
        assert row["cache_hit_kind"] == "none"
        assert row["latency_budget_passed"] == "True"
        assert row["cost_budget_passed"] == "True"
    with_pdf = [r for r in rows if r["attachment_size_kb"] == "5"]
    assert all(int(r["attachments_total_chars"]) > 0 for r in with_pdf)
    first, second = rows[0], rows[1]
    assert (first["turn_index"], second["turn_index"]) == ("1", "2")
    assert first["memory_drift_passed"] == ""  # turn 1 is trivial
    assert second["memory_drift_passed"] in {"True", "False"}


def test_runner_records_a_400_as_an_error_row(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.attachments.MAX_ATTACHMENTS_CHARS", 100)
    out = tmp_path / "smoke.csv"
    total = run_stress(client, [get_scenario("pivot")], [5], 1, _config(tmp_path), out, max_turns=3)

    assert total == 1  # the failed first turn aborts the session
    (row,) = _read(out)
    assert row["status_code"] == "400"
    assert row["error"].startswith("HTTP 400")
    assert row["turn_index"] == ""


def test_build_pdfs_is_deterministic_and_close_to_target(tmp_path: Path) -> None:
    first = build_all(tmp_path / "a", [5])
    second = build_all(tmp_path / "b", [5])
    assert first[0].read_bytes() == second[0].read_bytes()
    assert first[0] == pdf_path(tmp_path / "a", 5)
    assert 0.8 * 5 * 1024 <= extracted_chars(first[0]) <= 1.3 * 5 * 1024
