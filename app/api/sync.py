import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import SyncJobCreate, SyncJobResponse
from app.services.sync_service import SyncService

router = APIRouter(prefix="/v1/sync/jobs", tags=["Sync"])

@router.post("", response_model=SyncJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_sync_job(request: SyncJobCreate, db: Session = Depends(get_db)):
    return SyncService.response(db, SyncService.create(db, request))

@router.get("/{job_id}", response_model=SyncJobResponse)
def get_sync_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    return SyncService.response(db, SyncService.get(db,job_id))