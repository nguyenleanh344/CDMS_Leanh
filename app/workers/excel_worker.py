from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.core.db import SessionLocal
from app.models import ProcessingJob
from app.services.excel_import_service import process_excel_job


def run_once() -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = (db.query(ProcessingJob)
               .filter(
                   ProcessingJob.job_type == "EXCEL",
                   ProcessingJob.input_complete.is_(True),
                   or_(
                       ProcessingJob.status == "PENDING",
                       (ProcessingJob.status == "PROCESSING")
                       & (ProcessingJob.started_at < now - timedelta(hours=1)),
                   ),
               )
               .order_by(ProcessingJob.created_at)
               .with_for_update(skip_locked=True).first())
        if job is None:
            return False
        process_excel_job(db, job)
        return True


if __name__ == "__main__":
    run_once()
