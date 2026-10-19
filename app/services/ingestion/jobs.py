"""Ingestion job tracking: the domain view of a job and the repository contract.

A job moves ``pending -> running -> completed | failed``. Services depend on the
``JobsRepository`` Protocol; the Postgres implementation lives in
``app/persistence`` and the in-memory one below serves tests and scripts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, Protocol

JobStatusName = Literal["pending", "running", "completed", "failed"]

_MAX_ERROR_LEN = 2048


@dataclass(frozen=True)
class Job:
    job_id: uuid.UUID
    source_name: str
    status: JobStatusName
    documents_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class JobsRepository(Protocol):
    def create(self, source_name: str) -> Job: ...

    def get(self, job_id: uuid.UUID) -> Job | None: ...

    def mark_running(self, job_id: uuid.UUID) -> None: ...

    def mark_completed(self, job_id: uuid.UUID, *, documents_count: int) -> None: ...

    def mark_failed(self, job_id: uuid.UUID, *, error_message: str) -> None: ...

    def list_jobs(self, *, limit: int = 50) -> list[Job]: ...


class InMemoryJobsRepository:
    """Dict-backed repository for tests and one-off scripts."""

    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, Job] = {}

    def create(self, source_name: str) -> Job:
        job = Job(
            job_id=uuid.uuid4(),
            source_name=source_name,
            status="pending",
            documents_count=0,
            error_message=None,
            started_at=datetime.now(UTC),
            finished_at=None,
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self._jobs.get(job_id)

    def mark_running(self, job_id: uuid.UUID) -> None:
        self._update(job_id, status="running")

    def mark_completed(self, job_id: uuid.UUID, *, documents_count: int) -> None:
        self._update(
            job_id,
            status="completed",
            documents_count=documents_count,
            finished_at=datetime.now(UTC),
        )

    def mark_failed(self, job_id: uuid.UUID, *, error_message: str) -> None:
        self._update(
            job_id,
            status="failed",
            error_message=error_message[:_MAX_ERROR_LEN],
            finished_at=datetime.now(UTC),
        )

    def list_jobs(self, *, limit: int = 50) -> list[Job]:
        ordered = sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)
        return ordered[:limit]

    def _update(self, job_id: uuid.UUID, **fields: object) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            self._jobs[job_id] = replace(job, **fields)  # type: ignore[arg-type]
