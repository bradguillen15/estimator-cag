#!/usr/bin/env python3
"""Compare the full-precision HNSW index against the halfvec HNSW index.

Session 8 live, block 4.2. Runs the five benchmark queries twice, once per index, and prints top-5 ids, overlap
and latency side by side, to confirm empirically that half-precision storage does not change the results for this
corpus.

How each index is forced (the clean, non-destructive way): Postgres only uses an index whose indexed expression
matches the query, so

* ``ORDER BY embedding <=> :q``                    -> ``chunks_embedding_idx`` (full-precision
  ``vector_cosine_ops``, the teaching index from ``sql/01_create_hnsw.sql``);
* ``ORDER BY (embedding::halfvec(1536)) <=> :q``   -> ``chunks_embedding_halfvec_idx`` (``halfvec_cosine_ops``,
  created by migration 0003), the exact statement ``PostgresChunkStore.search`` runs.

No index is dropped. The script verifies the routing with ``EXPLAIN`` and prints which index each plan used.

Requires both indexes: ``alembic upgrade head`` (halfvec) and ``scripts/s08/sql/01_create_hnsw.sql`` (vector).

Usage (from the repo root)::

    uv run python scripts/s08/compare_indexes_s08.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from s08_common import (
    EmbeddedQuery,
    Stopwatch,
    embed_benchmark_queries,
    format_table,
    get_session_factory,
    require_embedder,
    truncate,
    vector_literal,
)

from app.persistence.models import EMBEDDING_DIMENSIONS, ChunkRow
from app.persistence.repositories.chunks import _search_statement

K = 5
WARMUP_RUNS = 1
MEASURED_RUNS = 2
VECTOR_INDEX = "chunks_embedding_idx"
HALFVEC_INDEX = "chunks_embedding_halfvec_idx"


async def assert_indexes_exist(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'"))
    names = {row.indexname for row in result}
    missing = {VECTOR_INDEX, HALFVEC_INDEX} - names
    if missing:
        print(
            f"ERROR: missing index(es) on chunks: {', '.join(sorted(missing))}.\n"
            "Create them first: `alembic upgrade head` (halfvec) and scripts/s08/sql/01_create_hnsw.sql (vector).",
            file=sys.stderr,
        )
        raise SystemExit(1)


def vector_statement(vector: list[float]):
    """Top-K ordered by the plain column: only the full-precision index can serve it."""
    return select(ChunkRow.id).order_by(ChunkRow.embedding.cosine_distance(vector)).limit(K)


async def index_used_by_plan(session: AsyncSession, order_by_sql: str, vector: list[float]) -> str:
    """Run EXPLAIN and report which index (if any) the plan uses."""
    literal = vector_literal(vector)
    explain = text(f"EXPLAIN SELECT id FROM chunks ORDER BY {order_by_sql.format(q=literal)} LIMIT {K}")
    plan = "\n".join(row[0] for row in await session.execute(explain))
    for index_name in (VECTOR_INDEX, HALFVEC_INDEX):
        if index_name in plan:
            return index_name
    return "seq scan"


async def timed_top_ids(run_query: Callable[[], Awaitable[list[int]]]) -> tuple[list[int], float]:
    """1 warm-up + 2 measured runs; return (top ids, mean latency ms)."""
    samples: list[float] = []
    top_ids: list[int] = []
    for run in range(WARMUP_RUNS + MEASURED_RUNS):
        with Stopwatch() as timer:
            top_ids = await run_query()
        if run >= WARMUP_RUNS:
            samples.append(timer.elapsed_ms)
    return top_ids, statistics.fmean(samples)


async def compare(queries: list[EmbeddedQuery]) -> None:
    session_factory = get_session_factory()

    async with session_factory() as session:
        await assert_indexes_exist(session)

        # Confirm the expression-based routing before measuring anything.
        plan_vector = await index_used_by_plan(session, "embedding <=> '{q}'::vector", queries[0][2])
        plan_halfvec = await index_used_by_plan(
            session,
            f"(embedding::halfvec({EMBEDDING_DIMENSIONS})) <=> '{{q}}'::halfvec({EMBEDDING_DIMENSIONS})",
            queries[0][2],
        )
        print(f"Plan check, column expression uses: {plan_vector}")
        print(f"Plan check, halfvec cast expression uses: {plan_halfvec}")
        if plan_vector != VECTOR_INDEX or plan_halfvec != HALFVEC_INDEX:
            print(
                "WARNING: unexpected plan routing, the measurements below may not compare the two indexes. "
                "Check the EXPLAIN output in psql.",
                file=sys.stderr,
            )

        rows: list[list[str]] = []
        for _, query, vector in queries:

            async def via_vector_index() -> list[int]:
                return [row.id for row in await session.execute(vector_statement(vector))]

            async def via_halfvec_index() -> list[int]:
                return [row.id for row in await session.execute(_search_statement(vector, K))]

            vector_ids, vector_ms = await timed_top_ids(via_vector_index)
            halfvec_ids, halfvec_ms = await timed_top_ids(via_halfvec_index)
            overlap = len(set(vector_ids) & set(halfvec_ids))

            rows.append(
                [
                    truncate(query, 32),
                    ",".join(map(str, vector_ids)),
                    ",".join(map(str, halfvec_ids)),
                    f"{overlap}/{K}",
                    f"{vector_ms:.2f}",
                    f"{halfvec_ms:.2f}",
                ]
            )

    print()
    print(format_table(["query", "vector top-5", "halfvec top-5", "overlap", "vec_ms", "half_ms"], rows))
    print()
    print(
        "Expected for this corpus: overlap 5/5 on every query. Half precision is indistinguishable at retrieval "
        "time while the index is about half the size."
    )


def main() -> int:
    embedder = require_embedder()
    queries = embed_benchmark_queries(embedder)
    asyncio.run(compare(queries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
