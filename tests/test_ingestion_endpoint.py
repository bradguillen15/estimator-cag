import uuid
from collections.abc import Iterator
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_catalog, get_filesystem_loader, get_jobs_scope, get_parser_registry
from app.main import app
from app.services.ingestion.catalog import load_catalog
from app.services.ingestion.jobs import InMemoryJobsRepository
from app.services.ingestion.loaders import FileSystemLoader
from app.services.ingestion.parsers import default_registry

BASE = "/api/v1/ingestion"


@pytest.fixture
def jobs_repo() -> InMemoryJobsRepository:
    return InMemoryJobsRepository()


@pytest.fixture
def ingestion_client(jobs_repo: InMemoryJobsRepository) -> Iterator[TestClient]:
    catalog = load_catalog("data/catalog/catalog.yaml")
    app.dependency_overrides[get_catalog] = lambda: catalog
    app.dependency_overrides[get_filesystem_loader] = lambda: FileSystemLoader("data/seed")
    app.dependency_overrides[get_parser_registry] = default_registry
    app.dependency_overrides[get_jobs_scope] = lambda: (lambda: nullcontext(jobs_repo))
    yield TestClient(app)
    app.dependency_overrides.clear()


def _run(client: TestClient, source: str):
    return client.post(f"{BASE}/runs", json={"source_name": source})


def test_run_included_source_completes(ingestion_client: TestClient) -> None:
    response = _run(ingestion_client, "presupuestos_json")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    job = ingestion_client.get(f"{BASE}/jobs/{body['job_id']}").json()  # background task already ran
    assert job["status"] == "completed"
    assert job["documents_count"] == 6
    assert job["error_message"] is None


def test_review_source_is_rejected_with_decision(ingestion_client: TestClient) -> None:
    response = _run(ingestion_client, "transcripciones_txt")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["reason"] == "source_not_included"
    assert detail["decision"] == "review"
    assert detail["decision_reason"]


def test_unknown_source_is_404(ingestion_client: TestClient) -> None:
    response = _run(ingestion_client, "nope")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "unknown_source"


def test_unknown_job_is_404(ingestion_client: TestClient) -> None:
    response = ingestion_client.get(f"{BASE}/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["reason"] == "unknown_job"


def test_parser_failure_marks_job_failed(ingestion_client: TestClient, tmp_path) -> None:
    (tmp_path / "budgets").mkdir()
    (tmp_path / "budgets" / "BUDGET-BAD.json").write_text("{not json", encoding="utf-8")
    app.dependency_overrides[get_filesystem_loader] = lambda: FileSystemLoader(tmp_path)
    response = _run(ingestion_client, "presupuestos_json")
    assert response.status_code == 202  # the failure is reported on the job, not the POST
    job = ingestion_client.get(f"{BASE}/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "failed"
    assert job["error_message"]


def test_extra_body_field_is_422(ingestion_client: TestClient) -> None:
    response = ingestion_client.post(f"{BASE}/runs", json={"source_name": "x", "other": 1})
    assert response.status_code == 422
