"""POST /api/v1/ingestion/runs and GET /api/v1/ingestion/jobs/{job_id}. Logic lives in IngestionService."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.dependencies import get_ingestion_service
from app.schemas.ingestion import IngestionJobView, IngestionRunRequest, IngestionRunResponse
from app.services.ingestion.orchestrator import IngestionService

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

ServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]


@router.post("/runs", response_model=IngestionRunResponse, status_code=202)
def create_ingestion_run(
    body: IngestionRunRequest, background: BackgroundTasks, service: ServiceDep
) -> IngestionRunResponse:
    job = service.start_run(body.source_name)
    background.add_task(service.run, job.job_id, job.source_name)
    return IngestionRunResponse(job_id=job.job_id, source_name=job.source_name, status=job.status)


@router.get("/jobs/{job_id}", response_model=IngestionJobView)
def get_ingestion_job(job_id: uuid.UUID, service: ServiceDep) -> IngestionJobView:
    return IngestionJobView.model_validate(service.get_job(job_id), from_attributes=True)
