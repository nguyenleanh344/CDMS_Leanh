import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InboundEvent, ProcessingJob
from app.schemas import SyncJobCreate, SyncJobResponse

ACTIVE = ("PENDING", "PROCESSING", "RETRYING")
PENDING_EVENTS = ("RECEIVED", "PROCESSING", "RETRYING")
FAILED_EVENTS = ("FAILED", "VALIDATION_ERROR", "CONFLICT")

class SyncService:
    @staticmethod
    def create(db: Session, request: SyncJobCreate,) -> ProcessingJob:
        active = db.query(ProcessingJob).filter(
            ProcessingJob.job_type == "SYNC", ProcessingJob.status.in_(ACTIVE)).first()
        if active:
            raise HTTPException(409, f"Active sync job: {active.job_id}")
        
        job = ProcessingJob(
            job_id=uuid.uuid4(), job_type="SYNC", status="PENDING",
            parameters=request.model_dump(), input_complete=False, file_name=None
        )
        db.add(job)
        
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "An active sync job already exists") from None
        db.refresh(job)
        return job

    @staticmethod
    def get(db: Session, job_id: uuid.UUID) -> ProcessingJob:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.job_type != "SYNC":
            raise HTTPException(404, "SYNC job not found. ")
        return job
    
    @staticmethod
    def counters(db: Session, job_id: uuid.UUID) -> dict[str, int]:
        rows = (
            db.query(InboundEvent.status, func.count(InboundEvent.event_id))
            .filter(InboundEvent.job_id == job_id)
            .group_by(InboundEvent.status)
            .all()
        )
        counts = {event_status: int(total) for event_status, total in rows}

        return {
            "total_count": sum(counts.values()),
            "success_count": counts.get("SUCCESS", 0),
            "duplicate_count": counts.get("DUPLICATE", 0),
            "no_change_count": counts.get("NO_CHANGE", 0),
            "stale_count": counts.get("STALE", 0),
            "conflict_count": counts.get("CONFLICT", 0),
            "failed_count": counts.get("FAILED", 0)
                            + counts.get("VALIDATION_ERROR", 0),
            "pending_count": sum(
                counts.get(state, 0)
                for state in ("RECEIVED", "PROCESSING", "RETRYING")
            ),
        }
        
    @staticmethod
    def response(db:Session, job: ProcessingJob) -> SyncJobResponse:
        return SyncJobResponse(
            job_id=str(job.job_id), job_type=job.job_type, status=job.status,
            parameters=job.parameters, input_complete=job.input_complete,
            attempt_count=job.attempt_count, error_code=job.error_code,
            error_message=job.error_message, **SyncService.counters(db, job.job_id),
        )
        
    @staticmethod
    def finalize(db: Session, job: ProcessingJob) -> None:
        if not job.input_complete:
            return
        counts = SyncService.counters(db,job.job_id)
        if counts["pending_count"]:
            return
        failures = counts["failed_count"] + counts["conflict_count"]
        if failures == 0:
            job.status = "SUCCESS"
        elif failures == counts["total_count"]:
            job.status = "FAILED"
        else:
            job.status = "PARTIAL_SUCCESS"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()