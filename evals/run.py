"""CLI: run the golden dataset against the real model and report per-case and aggregate scores.

    uv run python -m evals.run [--case ID] [--threshold 0.8] [--prompt-version vN]

WARNING: every case is a real, billed LLM call. The response caches are never wired in, so each run
reaches the model.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.prompts.loader import PROMPT_VERSION, available_prompt_versions
from app.schemas.estimations import EstimationRequest
from evals.dataset import GoldenCase, load_dataset
from evals.metrics import MetricResult, run_all_metrics


class EvalService(Protocol):
    def prepare(self, request: EstimationRequest) -> EstimationRequest: ...

    def generate(self, request: EstimationRequest, prompt_version: str = ...) -> str: ...


@dataclass(frozen=True)
class CaseReport:
    case_id: str
    metrics: list[MetricResult]
    error: str | None = None

    @property
    def score(self) -> float:
        return sum(m.score for m in self.metrics) / len(self.metrics) if self.metrics else 0.0


def build_service() -> EvalService:
    """The production service without caches: evals must measure the model, not a replay."""
    from app.config import settings
    from app.services.estimation_service import EstimationService
    from app.services.llm.factory import get_llm_provider

    return EstimationService(provider=get_llm_provider(settings))


def evaluate_case(service: EvalService, case: GoldenCase, prompt_version: str) -> CaseReport:
    try:
        request = service.prepare(case.to_request())
        text = service.generate(request, prompt_version)
    except Exception as exc:  # one failing case must not abort the whole run
        return CaseReport(case.id, [], error=f"{type(exc).__name__}: {exc}")
    return CaseReport(case.id, run_all_metrics(case, text))


def aggregate_score(reports: Sequence[CaseReport]) -> float:
    return sum(r.score for r in reports) / len(reports) if reports else 0.0


def _passed(reports: Sequence[CaseReport], threshold: float) -> bool:
    """An errored case fails the run even if the aggregate score clears the threshold."""
    return not any(r.error for r in reports) and aggregate_score(reports) >= threshold


def format_report(reports: Sequence[CaseReport], threshold: float) -> str:
    lines = [f"{'case':<40} {'score':>5}  details"]
    for report in reports:
        if report.error:
            lines.append(f"{report.case_id:<40} {0.0:>5.2f}  ERROR {report.error}")
            continue
        details = "; ".join(f"{m.name}={'ok' if m.passed else 'FAIL'} ({m.details})" for m in report.metrics)
        lines.append(f"{report.case_id:<40} {report.score:>5.2f}  {details}")
    total = aggregate_score(reports)
    errored = sum(1 for r in reports if r.error)
    verdict = "PASS" if _passed(reports, threshold) else "FAIL"
    suffix = f", {errored} errored case(s)" if errored else ""
    lines.append(f"\naggregate score: {total:.2f} (threshold {threshold:.2f}{suffix}) -> {verdict}")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.run",
        description="Run the golden dataset against the real model. Makes billed API calls (one per case).",
    )
    parser.add_argument("--case", help="Run only the case with this id.")
    parser.add_argument("--threshold", type=float, default=0.8, help="Minimum aggregate score, 0-1 (default 0.8).")
    parser.add_argument("--prompt-version", default=PROMPT_VERSION, help=f"Prompt version (default {PROMPT_VERSION}).")
    return parser


def main(argv: Sequence[str] | None = None, service: EvalService | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 0 <= args.threshold <= 1:
        print("--threshold must be between 0 and 1", file=sys.stderr)
        return 2
    if args.prompt_version not in available_prompt_versions():
        print(f"Unknown prompt version {args.prompt_version!r}; use one of {', '.join(available_prompt_versions())}", file=sys.stderr)
        return 2
    cases = load_dataset()
    if args.case:
        cases = [case for case in cases if case.id == args.case]
        if not cases:
            print(f"Unknown case id {args.case!r}", file=sys.stderr)
            return 2
    try:
        service = service or build_service()
    except ValueError as exc:  # missing API key / bad LLM_MODELS
        print(f"Cannot build the LLM provider: {exc}", file=sys.stderr)
        return 2
    reports = [evaluate_case(service, case, args.prompt_version) for case in cases]
    print(format_report(reports, args.threshold))
    return 0 if _passed(reports, args.threshold) else 1


if __name__ == "__main__":
    raise SystemExit(main())
