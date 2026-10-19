"""Postgres-backed ``JobsRepository``. Callers see ``Job`` dataclasses, never ORM rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import IngestionJobRow
from app.services.ingestion.jobs import Job, JobStatusName

_MAX_ERROR_LEN = 2048


class SqlJobsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, source_name: str) -> Job:
        row = IngestionJobRow(source_name=source_name, status="pending")
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return _to_job(row)

    def get(self, job_id: uuid.UUID) -> Job | None:
        row = self._session.get(IngestionJobRow, job_id)
        return _to_job(row) if row is not None else None

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
        rows = self._session.execute(
            select(IngestionJobRow).order_by(IngestionJobRow.started_at.desc()).limit(limit)
        ).scalars()
        return [_to_job(row) for row in rows]

    def _update(self, job_id: uuid.UUID, **fields: Any) -> None:
        row = self._session.get(IngestionJobRow, job_id)
        if row is None:
            return
        for key, value in fields.items():
            setattr(row, key, value)
        self._session.commit()


def sql_jobs_scope(session_factory: sessionmaker[Session]) -> Any:
    """Return a ``JobsScope``: each ``with scope() as repo`` opens and closes its own session."""

    @contextmanager
    def scope() -> Iterator[SqlJobsRepository]:
        session = session_factory()
        try:
            yield SqlJobsRepository(session)
        finally:
            session.close()

    return scope


def _to_job(row: IngestionJobRow) -> Job:
    return Job(
        job_id=row.job_id,
        source_name=row.source_name,
        status=cast(JobStatusName, row.status),
        documents_count=row.documents_count,
        error_message=row.error_message,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )
