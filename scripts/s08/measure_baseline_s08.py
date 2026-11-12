#!/usr/bin/env python3
"""Measure SQL-side search latency over the five benchmark queries.

Session 8 live, block 2.1 (baseline before the index experiments) and block 2.2 (re-run right after creating an
index to expose the before/after gap).

Difference with ``scripts/query_examples.py``: that script goes through the HTTP endpoint and its timing includes
the OpenAI embedding round trip, which the index cannot influence. This one embeds each query ONCE upfront (billed
calls), then times only the SQL execution: 1 warm-up run (discarded) plus 2 measured runs per query, reporting
mean and deviation. It runs the exact statement ``POST /search`` runs (``PostgresChunkStore.search``).

Note: migration 0003 already creates the halfvec HNSW index, so by default this measures the indexed state. For a
sequential-scan baseline, run ``alembic downgrade -1`` first (and ``alembic upgrade head`` afterwards).

Usage (from the repo root, API stack up, schema migrated)::

    uv run python scripts/s08/measure_baseline_s08.py

At the end it prints the first query's embedding as a pgvector literal; paste it into
``scripts/s08/sql/02_test_antipatron.sql`` for the psql demos.
"""

from __future__ import annotations

import asyncio
import statistics

from s08_common import (
    EmbeddedQuery,
    Stopwatch,
    embed_benchmark_queries,
    format_table,
    latency_summary,
    require_embedder,
    truncate,
    vector_literal,
)

from app.dependencies import get_chunk_store

K = 5
WARMUP_RUNS = 1
MEASURED_RUNS = 2


async def measure(queries: list[EmbeddedQuery]) -> None:
    store = get_chunk_store()

    rows: list[list[str]] = []
    all_samples: list[float] = []

    for _, query, vector in queries:
        samples: list[float] = []
        result_count = 0
        for run in range(WARMUP_RUNS + MEASURED_RUNS):
            with Stopwatch() as timer:
                results = await store.search(vector, K)
            if run >= WARMUP_RUNS:  # discard warm-up
                samples.append(timer.elapsed_ms)
            result_count = len(results)

        mean = statistics.fmean(samples)
        deviation = statistics.stdev(samples) if len(samples) > 1 else 0.0
        all_samples.extend(samples)
        rows.append([truncate(query, 40), f"{mean:.2f}", f"{deviation:.2f}", str(result_count)])

    print()
    print(format_table(["query", "mean_ms", "stdev_ms", "results"], rows))
    print()
    print(f"Summary ({len(all_samples)} measured runs): {latency_summary(all_samples)}")


def main() -> int:
    embedder = require_embedder()
    queries = embed_benchmark_queries(embedder)

    asyncio.run(measure(queries))

    # The antipattern demo (02_test_antipatron.sql) needs a real query vector to paste into psql. Print the first
    # one last so it sits at the bottom of the scrollback, ready to copy.
    _, query, vector = queries[0]
    print()
    print(f'pgvector literal for query 1 ("{truncate(query, 60)}"):')
    print(vector_literal(vector))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
