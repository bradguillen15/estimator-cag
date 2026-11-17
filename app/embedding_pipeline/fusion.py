"""Reciprocal Rank Fusion (session 10): merge several ranked lists into one.

Why rank-based: the vector branch orders by cosine distance (0..2, lower is better) and the lexical branch by
``ts_rank_cd`` (unbounded, higher is better). Those numbers live on incomparable scales, so adding or normalizing
them needs tuning that breaks whenever the corpus or the query length changes. RRF throws the scores away and
uses only the POSITION of each document in each list, which is comparable by construction.
"""

from __future__ import annotations


def reciprocal_rank_fusion(rankings: list[list[int]], *, k: int) -> list[tuple[int, float]]:
    """Fuse ``rankings`` (best first, ids) into ``[(id, rrf_score), ...]``, best first.

    ``score(d) = sum over rankings of 1 / (k + rank_r(d))`` with ``rank`` **1-based** (the top document of a list
    has rank 1). A document absent from a ranking contributes nothing for it. A repeated id inside one ranking only
    counts at its first (best) position.

    ``k`` damps the head of each list: with a small ``k`` the first place dominates (1/(1+1)=0.5 vs 1/(1+2)=0.33),
    with the conventional ``k=60`` the gap between rank 1 and rank 2 is tiny (0.0164 vs 0.0161) and agreement
    between branches matters more than any single branch's top pick.

    Ties are broken deterministically: the document that appears earliest in the input (ranking order, then
    position) wins; this keeps the first ranking (the vector branch) as the preferred order on equal scores.
    """
    if k <= 0:
        raise ValueError(f"k must be a positive integer, got {k}")

    scores: dict[int, float] = {}
    first_seen: dict[int, int] = {}
    for ranking in rankings:
        seen_in_ranking: set[int] = set()
        for position, doc_id in enumerate(ranking, start=1):
            if doc_id in seen_in_ranking:
                continue
            seen_in_ranking.add(doc_id)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + position)
            first_seen.setdefault(doc_id, len(first_seen))

    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))
