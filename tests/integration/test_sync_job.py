import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.clients.inventory_client import InventoryError, InventoryPage
from app.core.db import get_db
from app.main import app
from app.models import InboundEvent, ProcessingJob, ProductChanges, ProductCurrent
from app.workers.sync_worker import process_job


@pytest.fixture(scope="module")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a migrated PostgreSQL CDMS_Test")
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql") or parsed.database != "CDMS_Test":
        pytest.fail("TEST_DATABASE_URL must target PostgreSQL CDMS_Test")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM cdms.processing_jobs LIMIT 0"))
            connection.execute(text("SELECT 1 FROM cdms.inbound_events LIMIT 0"))
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def context(engine):
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as api:
            yield db, api, 1 + uuid.uuid4().int % 2_000_000_000
    finally:
        app.dependency_overrides.clear()
        db.close()
        transaction.rollback()
        connection.close()


class FakeInventory:
    def __init__(self, products=(), failure=False):
        self.products = list(products)
        self.failure = failure
        self.calls = []

    def fetch_page(self, page_index, page_size):
        self.calls.append((page_index, page_size))
        if self.failure:
            raise InventoryError("Emulator unavailable")
        begin = (page_index - 1) * page_size
        return InventoryPage.model_validate({
            "data": self.products[begin:begin + page_size],
            "pagination": {
                "pageIndex": page_index, "pageSize": page_size,
                "totalCount": len(self.products),
            },
        })


def product(product_id, version=1, name="Product A"):
    return {
        "productId": product_id, "sku": f"SKU-{product_id}",
        "productName": name, "isActive": True, "xCdmsVersion": version,
    }


def create(context, page_size=2, max_products=10):
    db, api, _ = context
    response = api.post("/v1/sync/jobs", json={
        "page_size": page_size, "max_products": max_products,
    })
    assert response.status_code == 202, response.text
    job_id = uuid.UUID(response.json()["job_id"])
    job = db.get(ProcessingJob, job_id)
    return job


def run(db, job, fake):
    job.status = "PROCESSING"
    job.attempt_count += 1
    db.commit()
    process_job(db, job, fake)


def status(context, job):
    response = context[1].get(f"/v1/sync/jobs/{job.job_id}")
    assert response.status_code == 200
    return response.json()


def events(db, job):
    return (db.query(InboundEvent)
            .filter(InboundEvent.job_id == job.job_id)
            .order_by(InboundEvent.item_index).all())


def test_create_and_prevent_two_active_jobs(context):
    job = create(context)
    assert job.status == "PENDING" and not job.input_complete
    assert job.job_type == "SYNC" and job.file_name is None
    assert status(context, job)["total_count"] == 0
    assert context[1].post("/v1/sync/jobs", json={}).status_code == 409
    assert context[1].get(f"/v1/sync/jobs/{uuid.uuid4()}").status_code == 404


def test_polling_pages_mapping_new_products_and_counters(context):
    db, _, product_id = context
    job = create(context, page_size=2)
    fake = FakeInventory([product(product_id + offset) for offset in range(3)])
    run(db, job, fake)
    assert fake.calls == [(1, 2), (2, 2)]
    assert job.status == "SUCCESS" and job.input_complete
    assert [e.item_index for e in events(db, job)] == [1, 2, 3]
    assert all(e.channel == "POLLING" and e.external_event_id is None
               and e.status == "SUCCESS" for e in events(db, job))
    assert events(db, job)[0].payload == {
        "product_id": product_id, "sku": f"SKU-{product_id}",
        "name": "Product A", "is_active": True,
    }
    assert db.get(ProductCurrent, product_id).source_version == 1
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1
    assert status(context, job)["success_count"] == 3
    assert status(context, job)["total_count"] == 3


def test_existing_product_uses_processor_and_stale(context):
    db, _, product_id = context
    job = create(context)
    # One job can receive multiple versions; processor applies in item order.
    fake = FakeInventory([product(product_id, 2, "New")])
    run(db, job, fake)
    assert job.status == "SUCCESS"
    assert db.get(ProductCurrent, product_id).name == "New"
    next_job = create(context)
    run(db, next_job, FakeInventory([product(product_id, 1, "Old")]))
    assert events(db, next_job)[0].status == "STALE"
    assert db.get(ProductCurrent, product_id).name == "New"
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1


def test_same_version_duplicate_and_new_version_no_change(context):
    db, _, product_id = context
    for version, expected in ((1, "SUCCESS"), (1, "DUPLICATE"), (2, "NO_CHANGE")):
        job = create(context)
        run(db, job, FakeInventory([product(product_id, version)]))
        assert events(db, job)[0].status == expected
    assert db.get(ProductCurrent, product_id).source_version == 2
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1


def test_conflict_counts_as_failed_and_unchanged_current(context):
    db, _, product_id = context
    first = create(context)
    run(db, first, FakeInventory([product(product_id)]))
    job = create(context)
    run(db, job, FakeInventory([product(product_id, 1, "Different")]))
    assert status(context, job)["conflict_count"] == 1
    assert job.status == "FAILED"
    assert db.get(ProductCurrent, product_id).name == "Product A"


def test_fetch_failure_retries_without_partial_events(context):
    db, _, _ = context
    job = create(context)
    run(db, job, FakeInventory(failure=True))
    assert job.status == "RETRYING" and not job.input_complete
    assert job.next_attempt_at is not None and events(db, job) == []
    for _ in range(2):
        run(db, job, FakeInventory(failure=True))
    assert job.status == "FAILED" and job.attempt_count == 3


def test_resume_does_not_fetch_or_duplicate_event(context):
    db, _, product_id = context
    job = create(context)
    run(db, job, FakeInventory([product(product_id)]))
    original_event_id = events(db, job)[0].event_id
    # Simulate a worker restart after input commit and before finalization.
    job.status = "PROCESSING"
    db.commit()
    unavailable = FakeInventory(failure=True)
    process_job(db, job, unavailable)
    assert unavailable.calls == []
    assert job.status == "SUCCESS"
    assert [e.event_id for e in events(db, job)] == [original_event_id]
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1


def test_pending_events_block_finalization_and_resume(context):
    db, _, product_id = context
    job = create(context)
    fake = FakeInventory([product(product_id)])
    # The input commit survives a simulated crash before process_job processes events.
    from app.workers.sync_worker import _fetch_input
    _fetch_input(db, job, fake)
    assert job.input_complete and events(db, job)[0].status == "RECEIVED"
    unavailable = FakeInventory(failure=True)
    process_job(db, job, unavailable)
    assert unavailable.calls == []
    assert status(context, job)["pending_count"] == 0
    assert job.status == "SUCCESS"


def test_partial_success_and_failed_counters(context):
    db, _, product_id = context
    job = create(context)
    from app.workers.sync_worker import _fetch_input
    _fetch_input(db, job, FakeInventory([product(product_id), product(product_id + 1)]))
    second = events(db, job)[1]
    second.payload = {"sku": "broken"}  # processor fails this event only
    db.commit()
    process_job(db, job, FakeInventory(failure=True))
    result = status(context, job)