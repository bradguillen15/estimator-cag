"""Pure helpers of the retrieval measurement script (the runner itself needs live services)."""

import pytest

from evals.retrieval.run import chunks_per_budget, load_golden, max_achievable, percentile, precision_at


def test_golden_set_labels_exist_in_the_corpus() -> None:
    counts = chunks_per_budget()

    for entry in load_golden():
        assert entry["query"] and entry["relevant_budget_ids"]
        assert set(entry["relevant_budget_ids"]) <= set(counts)


def test_precision_chunk_and_budget_level() -> None:
    chunk_p, budget_p = precision_at(["A", "A", "B", "C", "A"], {"A", "B"}, top=5)

    assert chunk_p == pytest.approx(4 / 5)
    assert budget_p == pytest.approx(2 / 3)
    assert precision_at([], {"A"}, top=5) == (0.0, 0.0)


def test_max_achievable_is_capped_by_relevant_chunks_and_top() -> None:
    assert max_achievable({"A", "B"}, {"A": 2, "B": 1}, top=5) == pytest.approx(3 / 5)
    assert max_achievable({"A"}, {"A": 9}, top=5) == 1.0


def test_percentile() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0, 100.0], 95) == 100.0
    assert percentile([5.0], 95) == 5.0
