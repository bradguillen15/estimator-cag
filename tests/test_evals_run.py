"""Runner behaviour with a fake service: exit codes, filtering, error isolation."""

import pytest

from app.schemas.estimations import EstimationRequest
from evals import run
from evals.dataset import load_dataset


class FakeEvalService:
    """Answers every case with a fixed text (or raises), recording the prompt versions used."""

    def __init__(self, text: str = "", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def prepare(self, request: EstimationRequest) -> EstimationRequest:
        return request

    def generate(self, request: EstimationRequest, prompt_version: str = "v3") -> str:
        self.calls.append((request.description, prompt_version))
        if self.error:
            raise self.error
        return self.text


def test_good_answer_exits_zero_and_prints_table(capsys: pytest.CaptureFixture[str]) -> None:
    case = next(c for c in load_dataset() if not c.insufficient_information)
    total = int((case.min_hours + case.max_hours) / 2)  # type: ignore[operator]
    label = "Total estimate" if case.language.value == "en" else "Total estimado"
    text = f"## Title\n\n{' '.join(case.expected_keywords)}\n\n**{label}: {total} hours**"
    service = FakeEvalService(text)
    assert run.main(["--case", case.id, "--threshold", "0.9"], service=service) == 0
    out = capsys.readouterr().out
    assert case.id in out and "aggregate score: 1.00" in out
    assert len(service.calls) == 1


def test_bad_answer_exits_nonzero() -> None:
    assert run.main(["--threshold", "0.8"], service=FakeEvalService("nonsense")) == 1


def test_provider_error_is_reported_per_case_and_fails(capsys: pytest.CaptureFixture[str]) -> None:
    service = FakeEvalService(error=RuntimeError("boom"))
    assert run.main([], service=service) == 1
    assert "ERROR RuntimeError: boom" in capsys.readouterr().out
    assert len(service.calls) == len(load_dataset())  # a failure did not abort the run


def test_prompt_version_is_forwarded() -> None:
    service = FakeEvalService("x")
    run.main(["--case", load_dataset()[0].id, "--prompt-version", "v2"], service=service)
    assert service.calls[0][1] == "v2"


@pytest.mark.parametrize(
    "argv", [["--case", "nope"], ["--threshold", "1.5"], ["--prompt-version", "v999"]]
)
def test_invalid_arguments_exit_two(argv: list[str]) -> None:
    service = FakeEvalService("x")
    assert run.main(argv, service=service) == 2
    assert service.calls == []


def test_build_service_has_no_caches() -> None:
    service = run.build_service()
    assert type(service._cache).__name__ == "NoOpCache"  # type: ignore[attr-defined]
    assert type(service._semantic).__name__ == "NoOpSemanticCache"  # type: ignore[attr-defined]
