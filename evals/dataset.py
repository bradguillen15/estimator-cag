"""Golden dataset: typed, validated loading of ``golden_dataset.json``."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.estimations import DetailLevel, EstimationRequest, OutputFormat, ProjectType, ResponseLanguage

DEFAULT_DATASET_PATH = Path(__file__).with_name("golden_dataset.json")


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=20, max_length=20000)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat
    language: ResponseLanguage
    min_hours: float | None = Field(default=None, ge=0)
    max_hours: float | None = Field(default=None, ge=0)
    expected_keywords: list[str] = Field(default_factory=list)
    # The model is expected to ask for more information instead of estimating.
    insufficient_information: bool = False

    @model_validator(mode="after")
    def _check_bounds(self) -> "GoldenCase":
        if self.insufficient_information:
            if self.min_hours is not None or self.max_hours is not None:
                raise ValueError("an insufficient-information case must not declare hour bounds")
        elif self.min_hours is None or self.max_hours is None or self.min_hours > self.max_hours:
            raise ValueError("an estimating case needs min_hours <= max_hours")
        return self

    def to_request(self) -> EstimationRequest:
        return EstimationRequest(
            description=self.description,
            project_type=self.project_type,
            detail_level=self.detail_level,
            output_format=self.output_format,
            language=self.language,
        )


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[GoldenCase]:
    """Loads and validates the cases; duplicate ids or an empty file are errors."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = [GoldenCase.model_validate(item) for item in raw]
    if not cases:
        raise ValueError(f"{path} contains no cases")
    ids = [case.id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate case ids: {', '.join(duplicates)}")
    return cases
