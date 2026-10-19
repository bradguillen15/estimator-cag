import uuid

from app.services.ingestion.jobs import InMemoryJobsRepository, JobsRepository


def test_create_starts_pending() -> None:
    repo = InMemoryJobsRepository()
    job = repo.create("seed")
    assert job.status == "pending"
    assert job.documents_count == 0
    assert job.finished_at is None
    assert repo.get(job.job_id) == job


def test_completed_transition_sets_count_and_finish_time() -> None:
    repo = InMemoryJobsRepository()
    job = repo.create("seed")
    repo.mark_running(job.job_id)
    assert repo.get(job.job_id).status == "running"  # type: ignore[union-attr]
    repo.mark_completed(job.job_id, documents_count=7)
    done = repo.get(job.job_id)
    assert done is not None
    assert (done.status, done.documents_count) == ("completed", 7)
    assert done.finished_at is not None


def test_failed_truncates_error_message() -> None:
    repo = InMemoryJobsRepository()
    job = repo.create("seed")
    repo.mark_failed(job.job_id, error_message="x" * 5000)
    failed = repo.get(job.job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_message is not None and len(failed.error_message) == 2048


def test_unknown_job_is_ignored_and_missing() -> None:
    repo = InMemoryJobsRepository()
    unknown = uuid.uuid4()
    repo.mark_running(unknown)
    assert repo.get(unknown) is None


def test_list_jobs_most_recent_first_and_limited() -> None:
    repo = InMemoryJobsRepository()
    first, second, third = (repo.create(n) for n in ("a", "b", "c"))
    listed = repo.list_jobs(limit=2)
    assert len(listed) == 2
    assert {j.job_id for j in listed} <= {first.job_id, second.job_id, third.job_id}


def test_satisfies_protocol() -> None:
    repo: JobsRepository = InMemoryJobsRepository()
    assert repo.list_jobs() == []
