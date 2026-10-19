"""CAG stress runner: where does the session pipeline break under load?

Walks ``scenarios x attachment sizes x repeats`` against the session API. Per turn it:

1. POSTs ``/api/v1/sessions/{id}/estimate`` (multipart) with the turn's transcript and the
   pre-built PDF (none for size 0).
2. Reads ``observation`` from the response (no log parsing).
3. GETs ``/api/v1/sessions/{id}`` for the post-turn snapshot used by ``MemoryDriftMetric``.
4. Writes one CSV row: telemetry, wall clock, HTTP status and three metric verdicts.

A non-2xx turn (e.g. HTTP 400 when attachments exceed the 60,000-char cap) is recorded as a
row with its status code and error, and aborts that session; it never crashes the run.

Two transports:

- ``--http URL``  httpx against a live server.
- (default)       in-process ``TestClient(app)`` with the providers from ``settings``.
                  WARNING: that makes REAL, BILLED LLM calls. Set ``LLM_MODELS`` to one cheap
                  model first, e.g. ``LLM_MODELS='["openai/gpt-4o-mini"]'``.

    uv run python -m evals.stress.run --http http://localhost:8000 --repeats 3
"""

import argparse
import csv
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.schemas.sessions import TurnObservation
from evals.stress.fixtures.build_pdfs import DEFAULT_DIR, TARGETS_KB, build_all, pdf_path
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import Scenario, ScenarioTurn, get_scenario

API_PREFIX = "/api/v1"
_ATTACHMENT_FIELD = "attachments"

CSV_COLUMNS = [
    "scenario",
    "attachment_size_kb",
    "repeat",
    "turn_index",
    "session_id",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "wall_clock_ms",
    "cache_hit_kind",
    "last_resolved_tier",
    "status_code",
    "latency_budget_passed",
    "cost_budget_passed",
    "memory_drift_passed",
    "tracked_fact",
    "error",
]

Files = list[tuple[str, tuple[str, bytes, str]]]


class Client(Protocol):
    """The slice of ``httpx.Client`` the runner uses (``TestClient`` satisfies it too)."""

    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...

    def get(self, url: str, **kwargs: Any) -> httpx.Response: ...


@dataclass(frozen=True)
class RunConfig:
    latency_metric: LatencyBudgetMetric
    cost_metric: CostBudgetMetric
    fixtures_dir: Path = DEFAULT_DIR


# -- transport ---------------------------------------------------------------


@contextmanager
def open_client(http_base_url: str | None) -> Iterator[Client]:
    """``--http`` gives a real httpx client; otherwise an in-process ``TestClient`` (billed LLM calls)."""
    if http_base_url:
        with httpx.Client(base_url=http_base_url, timeout=180.0) as client:
            yield client
        return

    from fastapi.testclient import TestClient

    from app.config import settings
    from app.dependencies import get_session_store
    from app.main import app
    from app.services.sessions import SessionStore

    store = SessionStore(max_turns=settings.session_max_turns, max_anchors=settings.session_max_anchors)
    app.dependency_overrides[get_session_store] = lambda: store
    try:
        with TestClient(app, raise_server_exceptions=False, timeout=180.0) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session_store, None)


# -- fixtures ----------------------------------------------------------------


def load_attachments(size_kb: int, fixtures_dir: Path = DEFAULT_DIR) -> Files | None:
    """The PDF for ``size_kb`` as multipart files (``None`` for 0); built deterministically if missing."""
    if size_kb == 0:
        return None
    if size_kb not in TARGETS_KB:
        raise ValueError(f"unsupported attachment size {size_kb} KB; available: 0, {', '.join(map(str, TARGETS_KB))}")
    path = pdf_path(fixtures_dir, size_kb)
    if not path.exists():
        build_all(fixtures_dir, [size_kb])
    return [(_ATTACHMENT_FIELD, (path.name, path.read_bytes(), "application/pdf"))]


# -- per-turn execution ------------------------------------------------------


def _form_body(scenario: Scenario, turn: ScenarioTurn) -> dict[str, str]:
    return {
        "transcript": turn.transcript,
        "project_type": scenario.project_type.value,
        "detail_level": scenario.detail_level.value,
        "output_format": scenario.output_format.value,
    }


def _http_error(response: httpx.Response) -> str:
    return f"HTTP {response.status_code}: {response.text[:200]}"


def _run_turn(
    client: Client, session_id: str, scenario: Scenario, turn: ScenarioTurn, files: Files | None
) -> tuple[int, TurnObservation | None, dict[str, Any] | None, int, str]:
    """One POST estimate + one GET snapshot -> ``(status, observation, snapshot, wall_ms, error)``."""
    start = time.perf_counter()
    try:
        response = client.post(
            f"{API_PREFIX}/sessions/{session_id}/estimate", data=_form_body(scenario, turn), files=files
        )
    except httpx.HTTPError as exc:
        return 0, None, None, int((time.perf_counter() - start) * 1000), f"{type(exc).__name__}: {str(exc)[:200]}"
    wall_ms = int((time.perf_counter() - start) * 1000)
    if not response.is_success:
        return response.status_code, None, None, wall_ms, _http_error(response)

    raw = response.json().get("observation")
    if raw is None:
        return response.status_code, None, None, wall_ms, "response has no observation"
    snapshot = client.get(f"{API_PREFIX}/sessions/{session_id}")
    if not snapshot.is_success:
        return snapshot.status_code, None, None, wall_ms, _http_error(snapshot)
    return response.status_code, TurnObservation(**raw), snapshot.json(), wall_ms, ""


def run_one_session(
    client: Client,
    scenario: Scenario,
    size_kb: int,
    repeat: int,
    config: RunConfig,
    writer: "csv.DictWriter[str]",
) -> int:
    """Walk the scenario once in a fresh session. Returns the rows written."""
    files = load_attachments(size_kb, config.fixtures_dir)
    created = client.post(f"{API_PREFIX}/sessions")
    created.raise_for_status()
    session_id = created.json()["session_id"]

    first = scenario.turns[0]
    drift_metric = MemoryDriftMetric(first.fact_introduced, first.fact_where) if first.fact_introduced else None

    rows = 0
    for turn in scenario.turns:
        row: dict[str, Any] = {
            "scenario": scenario.name,
            "attachment_size_kb": size_kb,
            "repeat": repeat,
            "session_id": session_id,
            "tracked_fact": first.fact_introduced or "",
        }
        status, observation, snapshot, wall_ms, error = _run_turn(client, session_id, scenario, turn, files)
        row.update(status_code=status, wall_clock_ms=wall_ms, error=error)
        if observation is None or snapshot is None:
            writer.writerow(row)
            rows += 1
            break  # a failed turn would skew memory drift for the rest of the session

        # Turn 1 trivially remembers itself: leave the drift column blank.
        drift = "" if drift_metric is None or observation.turn_index == 1 else drift_metric.evaluate(snapshot).passed
        row.update(
            observation.model_dump(mode="json"),
            latency_budget_passed=config.latency_metric.evaluate(observation).passed,
            cost_budget_passed=config.cost_metric.evaluate(observation).passed,
            memory_drift_passed=drift,
        )
        writer.writerow(row)
        rows += 1
    return rows


def run_stress(
    client: Client,
    scenarios: Sequence[Scenario],
    sizes: Sequence[int],
    repeats: int,
    config: RunConfig,
    output: Path,
    max_turns: int | None = None,
) -> int:
    """Run the whole matrix and write ``output``. Returns the total rows written."""
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for scenario in scenarios:
            if max_turns is not None:
                scenario = replace(scenario, turns=scenario.turns[:max_turns])
            for size_kb in sizes:
                for repeat in range(repeats):
                    print(f"  -> {scenario.name:<14} kb={size_kb:>3} repeat={repeat + 1}/{repeats}")
                    total += run_one_session(client, scenario, size_kb, repeat, config, writer)
                    fh.flush()
    return total


# -- reporting ---------------------------------------------------------------


def print_summary(csv_path: Path) -> None:
    """P50/P95 latency, total cost and drift pass rate per (scenario, size); error rows are counted apart."""
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    errors = 0
    with csv_path.open() as fh:
        for row in csv.DictReader(fh):
            if row["error"]:
                errors += 1
                continue
            groups.setdefault((row["scenario"], row["attachment_size_kb"]), []).append(row)

    header = f"{'scenario':<14} {'kb':>4} {'n':>4} {'P50 ms':>8} {'P95 ms':>8} {'tot $':>10} {'drift%':>7}"
    print("\nSummary (per scenario x attachment size)")
    print(header)
    print("-" * len(header))
    for (scenario, size_kb), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        latencies = sorted(float(r["latency_ms"]) for r in rows)
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        total_cost = sum(float(r["cost_usd"]) for r in rows)
        drifts = [r["memory_drift_passed"] for r in rows if r["memory_drift_passed"] != ""]
        drift_pct = 100.0 * sum(d == "True" for d in drifts) / len(drifts) if drifts else 0.0
        print(f"{scenario:<14} {size_kb:>4} {len(rows):>4} {p50:>8.0f} {p95:>8.0f} {total_cost:>10.4f} {drift_pct:>6.1f}%")
    print(f"\nError rows (non-2xx / transport): {errors}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--http", default=None, help="Base URL of a running API. Omit for in-process (BILLED real LLM).")
    parser.add_argument("--scenarios", default="growing,pivot,contradiction", help="Comma-separated scenario names.")
    parser.add_argument("--attachment-sizes", default="0,5,20,50,100", help="Comma-separated PDF sizes in KB (0 = none).")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=None, help="Cap the turns per scenario (default: all 20).")
    parser.add_argument("--latency-budget-ms", type=int, default=8000)
    parser.add_argument("--cost-budget-usd", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=Path("evals/stress/results.csv"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scenarios = [get_scenario(name.strip()) for name in args.scenarios.split(",")]
    sizes = [int(s) for s in args.attachment_sizes.split(",")]
    config = RunConfig(LatencyBudgetMetric(args.latency_budget_ms), CostBudgetMetric(args.cost_budget_usd))
    for kb in sizes:  # build missing PDFs now, not mid-run
        load_attachments(kb, config.fixtures_dir)

    mode = f"HTTP {args.http}" if args.http else "in-process TestClient (REAL, BILLED LLM calls)"
    print(f"Stress run [{mode}]: {len(scenarios)} scenarios x {len(sizes)} sizes x {args.repeats} repeats")
    start = time.perf_counter()
    with open_client(args.http) as client:
        total = run_stress(client, scenarios, sizes, args.repeats, config, args.output, args.max_turns)
    print(f"\nWrote {total} rows to {args.output} in {int(time.perf_counter() - start)}s")
    print_summary(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
