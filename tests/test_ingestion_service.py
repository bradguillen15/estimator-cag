from contextlib import nullcontext

import pytest

from app.exceptions import IngestionJobNotFoundError, IngestionSourceNotFoundError, IngestionSourceNotIncludedError
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.jobs import InMemoryJobsRepository
from app.services.ingestion.loaders import FileSystemLoader
from app.services.ingestion.orchestrator import IngestionService
from app.services.ingestion.parsers import default_registry


def _service(repo: InMemoryJobsRepository, data_root: str = "data/seed") -> IngestionService:
    return IngestionService(
        catalog=load_catalog("data/catalog/catalog.yaml"),
        loader=FileSystemLoader(data_root),
        registry=default_registry(),
        jobs_scope=lambda: nullcontext(repo),
    )


def test_start_run_creates_pending_job() -> None:
    repo = InMemoryJobsRepository()
    job = _service(repo).start_run("presupuestos_json")
    assert job.status == "pending"
    assert repo.get(job.job_id) == job


def test_start_run_rejects_unknown_and_not_included_without_creating_a_job() -> None:
    repo = InMemoryJobsRepository()
    service = _service(repo)
    with pytest.raises(IngestionSourceNotFoundError):
        service.start_run("nope")
    with pytest.raises(IngestionSourceNotIncludedError) as info:
        service.start_run("transcripciones_txt")
    assert info.value.decision == "review"
    assert repo.list_jobs() == []


def test_run_completes_job() -> None:
    repo = InMemoryJobsRepository()
    service = _service(repo)
    job = service.start_run("presupuestos_json")
    service.run(job.job_id, job.source_name)
    done = service.get_job(job.job_id)
    assert (done.status, done.documents_count) == ("completed", 6)


def test_run_never_raises_and_marks_failed_on_missing_location(tmp_path) -> None:
    repo = InMemoryJobsRepository()
    service = _service(repo, data_root=str(tmp_path))  # location does not exist
    job = service.start_run("presupuestos_json")
    service.run(job.job_id, job.source_name)
    assert service.get_job(job.job_id).status == "failed"


def test_get_job_unknown_raises() -> None:
    import uuid

    with pytest.raises(IngestionJobNotFoundError):
        _service(InMemoryJobsRepository()).get_job(uuid.uuid4())
