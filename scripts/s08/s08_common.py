"""Shared helpers for the session 8 live benchmark scripts.

Not a script: imported by ``measure_baseline_s08.py``, ``sweep_ef_search_s08.py``, ``compare_indexes_s08.py``,
``report_index_sizes_s08.py`` and ``insert_synthetic_chunks_s08.py``. Centralizes:

* the ``sys.path`` bootstrap (repo root for ``app.*``, ``scripts/`` for ``query_examples``),
* the benchmark queries (imported from ``scripts/query_examples.py`` so both files can never drift apart),
* query embedding via the project's ``OpenAIEmbedder`` (``get_openai_embedder``),
* the async session factory built from ``settings.database_url``,
* latency statistics and the ``format_table`` pretty-printer.

Dev tool: it may import ``app.*``; ``app/`` never imports it, and it is not part of pytest or CI.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS_DIR.parent
for path in (ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402
from query_examples import QUERIES  # noqa: E402  (single source of truth for the benchmark)

from app.config import settings  # noqa: E402
from app.dependencies import get_openai_embedder  # noqa: E402
from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402
from app.persistence.database import build_async_engine, build_async_session_factory  # noqa: E402

# (label, query, embedding) triples used by every benchmark script.
EmbeddedQuery = tuple[str, str, list[float]]


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Async session factory on ``settings.database_url`` (the engine connects lazily)."""
    return build_async_session_factory(build_async_engine(settings.database_url))


def require_embedder() -> OpenAIEmbedder:
    """Return the project's embedder or exit with an actionable message."""
    embedder = get_openai_embedder()
    if embedder is None:
        print(
            "ERROR: no OpenAI client available (OPENAI_API_KEY missing).\n"
            "Set it in .env (or the environment) and run the script again.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return embedder


def embed_benchmark_queries(embedder: OpenAIEmbedder) -> list[EmbeddedQuery]:
    """Embed the five benchmark queries ONCE (billed embedding calls).

    The benchmark scripts time the SQL execution only: embedding latency is an OpenAI round trip the index cannot
    influence, so it is paid upfront here and kept out of every measurement.
    """
    print(f"Embedding {len(QUERIES)} benchmark queries (excluded from timings)...")
    return [(label, query, embedder.embed_one(query)) for label, query in QUERIES]


def vector_literal(vector: list[float]) -> str:
    """Render a vector as the pgvector text literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(component) for component in vector) + "]"


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Plain-text aligned table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "  ".join("-" * widths[i] for i in range(len(headers)))
    body = "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)
    return f"{line}\n{sep}\n{body}"


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


class Stopwatch:
    """Context manager that captures elapsed wall-clock milliseconds."""

    def __enter__(self) -> Stopwatch:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000


def latency_summary(samples_ms: list[float]) -> str:
    """One-line global summary: mean, median and p95 when samples allow it."""
    mean = statistics.fmean(samples_ms)
    median = statistics.median(samples_ms)
    parts = [f"mean={mean:.1f} ms", f"median={median:.1f} ms"]
    if len(samples_ms) >= 20:
        p95 = statistics.quantiles(samples_ms, n=20)[-1]
        parts.append(f"p95={p95:.1f} ms")
    return " | ".join(parts)
