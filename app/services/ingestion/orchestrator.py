"""Glue between catalog, loader and parser for one ingestion run, plus the use-case service.

``ingest_source`` assumes the source was already validated (``IngestionService.start_run``
is the single place that does it) and records progress in the jobs repository:
pending -> running -> completed | failed. No HTTP, no SQLAlchemy here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

import structlog

from app.exceptions import (
    IngestionJobNotFoundError,
    IngestionSourceNotFoundError,
    IngestionSourceNotIncludedError,
)
from app.services.ingestion.catalog import CatalogDecision, DataCatalog
from app.services.ingestion.documents import Document
from app.services.ingestion.jobs import Job, JobsRepository
from app.services.ingestion.loaders import FileSystemLoader
from app.services.ingestion.parsers import ParseContext, ParserRegistry

log = structlog.get_logger(__name__)

# Each call opens (and closes) its own unit of work, so a background run never
# shares a request-scoped session.
JobsScope = Callable[[], AbstractContextManager[JobsRepository]]


def ingest_source(
    *,
    catalog: DataCatalog,
    source_name: str,
    loader: FileSystemLoader,
    registry: ParserRegistry,
    jobs_repo: JobsRepository,
    job_id: uuid.UUID,
) -> list[Document]:
    """Parse every blob of ``source_name``; update the job row; re-raise any failure."""
    bound = log.bind(job_id=str(job_id), source_name=source_name)
    source = catalog.find(source_name)
    if source is None:
        raise IngestionSourceNotFoundError(source_name)

    jobs_repo.mark_running(job_id)
    bound.info("ingestion.started", format=source.format)

    documents: list[Document] = []
    try:
        parser = registry.get(source.format)
        context = ParseContext(source=source, source_version=catalog.version, ingested_at=datetime.now(UTC))
        for blob in loader.iter_blobs(source.location, {source.format}):
            documents.extend(parser.parse(blob, context))
    except Exception as exc:
        bound.error("ingestion.failed", error=str(exc))
        jobs_repo.mark_failed(job_id, error_message=str(exc))
        raise

    jobs_repo.mark_completed(job_id, documents_count=len(documents))
    bound.info("ingestion.completed", documents_count=len(documents))
    return documents


class IngestionService:
    def __init__(
        self,
        *,
        catalog: DataCatalog,
        loader: FileSystemLoader,
        registry: ParserRegistry,
        jobs_scope: JobsScope,
    ) -> None:
        self._catalog = catalog
        self._loader = loader
        self._registry = registry
        self._jobs_scope = jobs_scope

    def start_run(self, source_name: str) -> Job:
        """Validate the source against the catalog and create the pending job."""
        source = self._catalog.find(source_name)
        if source is None:
            raise IngestionSourceNotFoundError(source_name)
        if source.decision is not CatalogDecision.INCLUDE:
            raise IngestionSourceNotIncludedError(
                source_name, decision=source.decision.value, decision_reason=source.decision_reason
            )
        with self._jobs_scope() as repo:
            return repo.create(source_name)

    def run(self, job_id: uuid.UUID, source_name: str) -> None:
        """Background entry point: never raises (the job row carries the failure)."""
        try:
            with self._jobs_scope() as repo:
                ingest_source(
                    catalog=self._catalog,
                    source_name=source_name,
                    loader=self._loader,
                    registry=self._registry,
                    jobs_repo=repo,
                    job_id=job_id,
                )
        except Exception as exc:
            # ingest_source already marked the job failed for parse/load errors; this covers the rest.
            log.error("ingestion_background_failed", job_id=str(job_id), source_name=source_name, error=str(exc)[:400])
            self._mark_failed_best_effort(job_id, str(exc))

    def get_job(self, job_id: uuid.UUID) -> Job:
        with self._jobs_scope() as repo:
            job = repo.get(job_id)
        if job is None:
            raise IngestionJobNotFoundError(job_id)
        return job

    def _mark_failed_best_effort(self, job_id: uuid.UUID, message: str) -> None:
        try:
            with self._jobs_scope() as repo:
                job = repo.get(job_id)
                if job is not None and job.status not in ("completed", "failed"):
                    repo.mark_failed(job_id, error_message=message)
        except Exception as exc:
            log.error("ingestion_mark_failed_error", job_id=str(job_id), error=str(exc)[:400])
