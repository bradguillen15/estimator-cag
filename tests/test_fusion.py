"""Reciprocal Rank Fusion: pure function, no I/O."""

import pytest

from app.embedding_pipeline.fusion import reciprocal_rank_fusion


def test_score_is_sum_of_reciprocal_ranks_with_one_based_rank() -> None:
    fused = dict(reciprocal_rank_fusion([[1, 2], [2, 3]], k=60))

    assert fused[1] == pytest.approx(1 / 61)
    assert fused[2] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[3] == pytest.approx(1 / 62)


def test_document_in_both_branches_beats_single_branch_top_pick() -> None:
    fused = reciprocal_rank_fusion([[10, 20], [30, 20]], k=60)

    assert [doc for doc, _ in fused][0] == 20


def test_ties_keep_first_seen_order() -> None:
    # 1 and 2 are each first in one branch: equal score; the first ranking's document wins.
    assert [doc for doc, _ in reciprocal_rank_fusion([[1], [2]], k=60)] == [1, 2]
    assert [doc for doc, _ in reciprocal_rank_fusion([[2], [1]], k=60)] == [2, 1]


def test_duplicates_inside_one_ranking_count_once_at_best_position() -> None:
    fused = dict(reciprocal_rank_fusion([[1, 2, 1]], k=60))

    assert fused[1] == pytest.approx(1 / 61)
    assert fused[2] == pytest.approx(1 / 62)


def test_empty_branch_yields_the_other_ranking_order() -> None:
    assert [doc for doc, _ in reciprocal_rank_fusion([[3, 1, 2], []], k=60)] == [3, 1, 2]
    assert reciprocal_rank_fusion([[], []], k=60) == []
    assert reciprocal_rank_fusion([], k=60) == []


def test_smaller_k_widens_the_gap_between_ranks() -> None:
    small = dict(reciprocal_rank_fusion([[1, 2]], k=1))
    large = dict(reciprocal_rank_fusion([[1, 2]], k=60))

    assert small[1] / small[2] > large[1] / large[2]


@pytest.mark.parametrize("k", [0, -1])
def test_non_positive_k_raises(k: int) -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[1]], k=k)
