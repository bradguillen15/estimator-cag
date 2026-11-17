"""CLI: measure retrieval quality (precision@5) and latency for the four search configurations.

    uv run python -m evals.retrieval.run [--repeats 5] [--top 5]

Configurations: A vector, B hybrid (vector + full-text, RRF), C vector + rerank, D hybrid + rerank.

WARNING: needs OPENAI_API_KEY (one billed embedding per golden query, embedded ONCE and reused by every
configuration), a live Postgres with the corpus ingested and migration 0004 applied, and the cross-encoder weights
(downloaded on first use). Never part of pytest/CI. The Markdown report is written to evals/retrieval/RESULTS.md
(overwritten on each run).

Labels: ``golden_set.json`` lists the budgets that are relevant to each query. Chunk-level precision@5 is the
fraction of the top-5 chunks that belong to a relevant budget; the maximum achievable value per query depends on how
many chunks the relevant budgets own (``min(5, relevant chunks) / 5``). Budget-level precision@5 is the share of the
distinct budgets in the top 5 that are relevant.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
GOLDEN_PATH = HERE / "golden_set.json"
RESULTS_PATH = HERE / "RESULTS.md"
BUDGETS_PATH = Path(__file__).resolve().parents[2] / "data" / "budgets_sample.json"

# (label, mode, rerank)
CONFIGS: list[tuple[str, str, bool]] = [
    ("A", "vector", False),
    ("B", "hybrid", False),
    ("C", "vector", True),
    ("D", "hybrid", True),
]


@dataclass
class QueryResult:
    config: str
    query_id: str
    chunk_p: float
    budget_p: float
    max_p: float
    latencies_ms: list[float]
    top_budgets: list[str]


@dataclass
class ConfigSummary:
    label: str
    mode: str
    rerank: bool
    results: list[QueryResult] = field(default_factory=list)

    @property
    def samples(self) -> list[float]:
        return [ms for result in self.results for ms in result.latencies_ms]


def load_golden(path: Path = GOLDEN_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def chunks_per_budget(path: Path = BUDGETS_PATH) -> dict[str, int]:
    """One chunk per budget component (see the structural chunker)."""
    budgets = json.loads(path.read_text(encoding="utf-8"))
    return {budget["budget_id"]: len(budget["components"]) for budget in budgets}


def precision_at(budget_ids: list[str], relevant: set[str], top: int) -> tuple[float, float]:
    """(chunk-level, budget-level) precision over the first ``top`` ranked chunks."""
    ranked = budget_ids[:top]
    if not ranked:
        return 0.0, 0.0
    chunk_p = sum(1 for budget_id in ranked if budget_id in relevant) / len(ranked)
    distinct = set(ranked)
    return chunk_p, len(distinct & relevant) / len(distinct)


def max_achievable(relevant: set[str], chunk_counts: dict[str, int], top: int) -> float:
    return min(top, sum(chunk_counts.get(budget_id, 0) for budget_id in relevant)) / top


def percentile(samples: list[float], pct: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))]


def render_report(
    summaries: list[ConfigSummary], golden: list[dict[str, Any]], *, repeats: int, top: int, cold_load_ms: float
) -> str:
    lines = [
        "# Retrieval evaluation: precision@%d and latency" % top,
        "",
        f"{len(golden)} golden queries, {repeats} repeats per query and configuration. Query embeddings are computed "
        "once per query and excluded from the latency (latency = retrieval + rerank only).",
        f"Reranker cold load (excluded from latencies): {cold_load_ms:.0f} ms.",
        "",
        "| Config | Search | Rerank | Mean P@%d chunk | Mean P@%d budget | Median latency ms | p95 latency ms |" % (top, top),
        "|---|---|---|---|---|---|---|",
    ]
    for summary in summaries:
        medians = [statistics.median(r.latencies_ms) for r in summary.results]
        lines.append(
            f"| {summary.label} | {summary.mode} | {'yes' if summary.rerank else 'no'} "
            f"| {statistics.mean(r.chunk_p for r in summary.results):.3f} "
            f"| {statistics.mean(r.budget_p for r in summary.results):.3f} "
            f"| {statistics.median(medians):.1f} | {percentile(summary.samples, 95):.1f} |"
        )
    max_mean = statistics.mean(r.max_p for r in summaries[0].results)
    lines += ["", f"Mean maximum achievable chunk P@{top} over the golden set: {max_mean:.3f}.", "", "## Per query", ""]
    lines += [
        f"| Query | Config | P@{top} chunk | Max P@{top} | P@{top} budget | Median ms | Top budgets |",
        "|---|---|---|---|---|---|---|",
    ]
    for query in golden:
        for summary in summaries:
            r = next(x for x in summary.results if x.query_id == query["id"])
            lines.append(
                f"| {r.query_id} | {r.config} | {r.chunk_p:.2f} | {r.max_p:.2f} | {r.budget_p:.2f} "
                f"| {statistics.median(r.latencies_ms):.1f} | {', '.join(r.top_budgets)} |"
            )
    lines.append("")
    return "\n".join(lines)


async def measure(repeats: int, top: int) -> str:
    # Imported here so --help works without settings, database or keys.
    from app.dependencies import get_openai_embedder, get_reranker, get_semantic_retriever

    retriever = get_semantic_retriever()
    embedder = get_openai_embedder()
    if retriever is None or embedder is None:
        raise SystemExit("OPENAI_API_KEY is not configured.")

    golden = load_golden()
    chunk_counts = chunks_per_budget()

    vectors = {
        query["id"]: await asyncio.to_thread(embedder.embed_one, query["query"]) for query in golden
    }  # one billed embedding per query, reused by every configuration

    reranker = get_reranker()
    started = time.perf_counter()
    await asyncio.to_thread(reranker.load)
    cold_load_ms = (time.perf_counter() - started) * 1000
    print(f"Reranker cold load: {cold_load_ms:.0f} ms")

    summaries: list[ConfigSummary] = []
    for label, mode, rerank in CONFIGS:
        summary = ConfigSummary(label, mode, rerank)
        # One discarded call per configuration: connection pool and first-batch effects stay out of the samples.
        first = golden[0]
        await retriever.search_with_vector(
            query=first["query"], query_vector=vectors[first["id"]], k=top, mode=mode, rerank=rerank
        )
        for query in golden:
            relevant = set(query["relevant_budget_ids"])
            latencies: list[float] = []
            response = None
            for _ in range(repeats):
                t0 = time.perf_counter()
                response = await retriever.search_with_vector(
                    query=query["query"], query_vector=vectors[query["id"]], k=top, mode=mode, rerank=rerank
                )
                latencies.append((time.perf_counter() - t0) * 1000)
            assert response is not None
            budget_ids = [hit.metadata.get("budget_id", "") for hit in response.results]
            chunk_p, budget_p = precision_at(budget_ids, relevant, top)
            summary.results.append(
                QueryResult(
                    label,
                    query["id"],
                    chunk_p,
                    budget_p,
                    max_achievable(relevant, chunk_counts, top),
                    latencies,
                    budget_ids[:top],
                )
            )
        summaries.append(summary)
        print(f"Config {label} ({mode}, rerank={rerank}) done")

    return render_report(summaries, golden, repeats=repeats, top=top, cold_load_ms=cold_load_ms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Precision@k and latency for search configurations A-D.")
    parser.add_argument("--repeats", type=int, default=5, help="Timed repeats per query and configuration.")
    parser.add_argument("--top", type=int, default=5, help="Rank cut-off for precision (and k without rerank).")
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.top < 1:
        parser.error("--repeats and --top must be >= 1")

    report = asyncio.run(measure(args.repeats, args.top))
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written to {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
