"""Pydantic schemas for the ingestion HTTP layer."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["pending", "running", "completed", "failed"]


class IngestionRunRequest(BaseModel):
    """Body of ``POST /api/v1/ingestion/runs``."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(
        min_length=1,
        max_length=128,
        description="Name of an ``include`` source in the catalog; unknown is 404, review/exclude is 400.",
    )


class IngestionRunResponse(BaseModel):
    """Response of ``POST /api/v1/ingestion/runs`` (HTTP 202)."""

    job_id: uuid.UUID
    source_name: str
    status: JobStatus


class IngestionJobView(BaseModel):
    """Response of ``GET /api/v1/ingestion/jobs/{job_id}``."""

    job_id: uuid.UUID
    source_name: str
    status: JobStatus
    documents_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
