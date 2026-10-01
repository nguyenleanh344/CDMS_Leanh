import os
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api import imports as imports_api
from app.core.db import get_db
from app.main import app
from app.models import InboundEvent, ProcessingJob, ProductChanges, ProductCurrent
from app.services.excel_import_service import HEADER, process_excel_job


@pytest.fixture(scope="module")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to migrated PostgreSQL CDMS_Test")
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql") or parsed.database != "CDMS_Test":
        pytest.fail("TEST_DATABASE_URL must target PostgreSQL CDMS_Test")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM cdms.processing_jobs LIMIT 0"))
            conn.execute(text("SELECT 1 FROM cdms.inbound_events LIMIT 0"))
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def context(engine, monkeypatch):
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    app.dependency_overrides[get_db] = lambda: db
    # TestClient executes BackgroundTasks before returning the response. Keep its
    # processing on the same transaction so the outer rollback isolates each test.
    monkeypatch.setattr(
        imports_api, "process_excel_in_background",
        lambda job_id: process_excel_job(db, db.get(ProcessingJob, job_id)),
    )
    try:
        with TestClient(app) as api:
            yield db, api, 1 + uuid.uuid4().int % 2_000_000_000
    finally:
        app.dependency_overrides.clear()
        db.close()
        outer.rollback()
        connection.close()


def xlsx(rows=(), header=HEADER, sheet="Products"):
    book = Workbook()
    tab = book.active
    tab.title = sheet
    tab.append(header)
    for row in rows:
        tab.append(row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def upload(api, content, filename="products.xlsx"):
    return api.post("/v1/imports/products", files={
        "file": (
            filename, content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    })


def events(db, batch_id):
    return (db.query(InboundEvent).filter_by(job_id=batch_id)
            .order_by(InboundEvent.item_index).all())


def test_mixed_valid_invalid_rows_update_products_and_errors(context):
    db, api, product_id = context
    response = upload(api, xlsx([
        (product_id, "SKU-A", "A", True, 1),
        (product_id + 1, "SKU-B", "Bad", "yes", 1),
        (product_id + 2, None, None, "false", 2),
    ]), "C:\\uploads\\products.xlsx")
    assert response.status_code == 202, response.text
    accepted = response.json()
    assert accepted["status"] == "PENDING" and accepted["total_count"] == 3
    batch_id = uuid.UUID(accepted["batch_id"])
    assert accepted["status_url"] == f"/v1/imports/{batch_id}"
    job = db.get(ProcessingJob, batch_id)
    assert (job.job_type, job.file_name, job.parameters, job.input_complete) == (
        "EXCEL", "products.xlsx", {}, True,
    )
    records = events(db, batch_id)
    assert [e.item_index for e in records] == [2, 3, 4]
    assert [e.status for e in records] == ["SUCCESS", "VALIDATION_ERROR", "SUCCESS"]
    assert records[1].payload is None and records[1].attempt_count == 0
    assert records[1].processed_at is not None
    assert records[1].error_code == "VALIDATION_ERROR"
    assert db.get(ProductCurrent, product_id).source_version == 1
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1
    result = api.get(f"/v1/imports/{batch_id}")
    assert result.status_code == 200
    assert result.json()["status"] == "PARTIAL_SUCCESS"
    assert result.json()["success_count"] == 2
    assert result.json()["failed_count"] == 1
    errors = api.get(f"/v1/imports/{batch_id}/errors")
    assert errors.status_code == 200
    assert [(r["item_index"], r["status"]) for r in errors.json()] == [
        (3, "VALIDATION_ERROR")
    ]


def test_existing_product_versions_and_resume(context):
    db, api, product_id = context
    response = upload(api, xlsx([
        (product_id, "SKU-A", "A", True, 1),
        (product_id, "SKU-A", "A", True, 1),
        (product_id, "SKU-A", "A", True, 2),
        (product_id, "SKU-A", "Old", True, 1),
        (product_id, "SKU-A", "Conflicting", True, 2),
    ]))
    batch_id = uuid.UUID(response.json()["batch_id"])
    assert [event.status for event in events(db, batch_id)] == [
        "SUCCESS", "DUPLICATE", "NO_CHANGE", "STALE", "CONFLICT",
    ]
    result = api.get(f"/v1/imports/{batch_id}").json()
    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["total_count"] == 5 and result["conflict_count"] == 1
    assert [e["item_index"] for e in api.get(f"/v1/imports/{batch_id}/errors").json()] == [6]
    assert db.get(ProductCurrent, product_id).source_version == 2
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1
    process_excel_job(db, db.get(ProcessingJob, batch_id))
    assert db.query(ProductChanges).filter_by(product_id=product_id).count() == 1


def test_all_invalid_and_empty_file(context):
    db, api, product_id = context
    bad = upload(api, xlsx([(product_id, None, None, "yes", 1)]))
    batch_id = uuid.UUID(bad.json()["batch_id"])
    assert api.get(f"/v1/imports/{batch_id}").json()["status"] == "FAILED"
    assert len(events(db, batch_id)) == 1
    empty = upload(api, xlsx())
    empty_id = uuid.UUID(empty.json()["batch_id"])
    assert api.get(f"/v1/imports/{empty_id}").json()["status"] == "SUCCESS"
    assert api.get(f"/v1/imports/{empty_id}").json()["total_count"] == 0


@pytest.mark.parametrize("filename,content", [
    ("products.xls", xlsx()),
    ("products.xlsx", b"broken workbook"),
    ("products.xlsx", xlsx(sheet="Other")),
    ("products.xlsx", xlsx(header=HEADER + ("extra",))),
    ("products.xlsx", b"x" * (5 * 1024 * 1024 + 1)),
],    ids=[
        "wrong-extension",
        "broken-workbook",
        "wrong-sheet",
        "wrong-header",
        "oversized-file",
    ],)
def test_invalid_file_does_not_create_job_or_event(context, filename, content):
    db, api, _ = context
    before_jobs = db.query(ProcessingJob).filter_by(job_type="EXCEL").count()
    before_events = db.query(InboundEvent).filter_by(channel="EXCEL").count()
    assert upload(api, content, filename).status_code in (413, 422)
    assert db.query(ProcessingJob).filter_by(job_type="EXCEL").count() == before_jobs
    assert db.query(InboundEvent).filter_by(channel="EXCEL").count() == before_events


def test_unknown_batch_returns_404(context):
    _, api, _ = context
    unknown = uuid.uuid4()
    assert api.get(f"/v1/imports/{unknown}").status_code == 404
    assert api.get(f"/v1/imports/{unknown}/errors").status_code == 404