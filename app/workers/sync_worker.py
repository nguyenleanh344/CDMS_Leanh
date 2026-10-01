import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.clients.inventory_client import InventoryClient, InventoryError
from app.core.db import SessionLocal
from app.models import InboundEvent, ProcessingJob
from app.services.product_processor import ProductProcessor
from app.services.sync_service import SyncService

MAX_ATTEMPTS = 3
LEASE = timedelta(hours=1)


def _mark_retry(db: Session, job: ProcessingJob, exc: Exception) -> None:
    job_id = job.job_id
    db.rollback()
    job = db.get(ProcessingJob, job_id, with_for_update=True)
    job.error_code = type(exc).__name__[:64]
    job.error_message = str(exc)[:1000]
    if job.attempt_count >= MAX_ATTEMPTS:
        job.status = "FAILED"
        job.finished_at = datetime.now(timezone.utc)
        job.next_attempt_at = None
    else:
        job.status = "RETRYING"
        job.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            seconds=30 * 2 ** (job.attempt_count - 1)
        )
    db.commit()


def _fetch_input(db: Session, job: ProcessingJob, client: InventoryClient) -> None:
    page_size = job.parameters["page_size"]
    limit = job.parameters["max_products"]
    products = []
    page_index = 1
    total = None
    seen_ids = set()

    while len(products) < limit:
        page = client.fetch_page(page_index, page_size)
        if total is None:
            total = page.pagination.totalCount
        elif page.pagination.totalCount != total:
            raise InventoryError("Emulator product count changed during pagination")
        if not page.data:
            if len(products) < min(total, limit):
                raise InventoryError("Emulator returned an incomplete product list")
            break
        for product in page.data:
            if product.productId in seen_ids:
                raise InventoryError("Emulator returned a product on multiple pages")
            seen_ids.add(product.productId)
            products.append(product)
            if len(products) >= limit:
                break
        if len(page.data) < page_size and len(products) < min(total, limit):
            raise InventoryError("Emulator returned an incomplete product page")
        if len(products) >= min(total, limit):
            break
        page_index += 1

    for index, product in enumerate(products, start=1):
        db.add(InboundEvent(
            event_id=uuid.uuid4(), job_id=job.job_id, item_index=index,
            channel="POLLING", external_event_id=None,
            product_id=product.productId, source_version=product.xCdmsVersion,
            raw_payload=product.model_dump(), payload=product.payload(), status="RECEIVED",
        ))
    job.input_complete = True
    db.commit()


def process_job(db: Session, job: ProcessingJob, client: InventoryClient) -> None:
    try:
        if not job.input_complete:
            _fetch_input(db, job, client)

        event_ids = [event_id for (event_id,) in (
            db.query(InboundEvent.event_id)
            .filter(InboundEvent.job_id == job.job_id,
                    InboundEvent.status.in_(("RECEIVED", "RETRYING")))
            .order_by(InboundEvent.item_index)
            .all()
        )]
        for event_id in event_ids:
            ProductProcessor.process(db, event_id)
            job.started_at = datetime.now(timezone.utc)  
            db.commit()

        SyncService.finalize(db, job)
    except Exception as exc:
        _mark_retry(db, job, exc)


def run_once(client: InventoryClient | None = None) -> bool:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.job_type == "SYNC",
                or_(
                    ProcessingJob.status == "PENDING",
                    (ProcessingJob.status == "RETRYING")
                    & (ProcessingJob.next_attempt_at <= now),
                    (ProcessingJob.status == "PROCESSING")
                    & (ProcessingJob.started_at < now - LEASE),
                ),
            )
            .order_by(ProcessingJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            return False
        job.status = "PROCESSING"
        job.started_at = now
        job.attempt_count += 1
        job.next_attempt_at = None
        db.commit()
        process_job(db, job, client or InventoryClient())
        return True
    
if __name__ == "__main__":
    run_once()