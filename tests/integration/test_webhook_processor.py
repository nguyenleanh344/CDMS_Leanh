
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.main import app
from app.models import InboundEvent, ProductChanges, ProductCurrent


@pytest.fixture(scope="module")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a migrated PostgreSQL cdms_test"
        )

    parsed = make_url(url)
    if (
        not parsed.drivername.startswith("postgresql")
        or parsed.database != "CDMS_Test"
    ):
        pytest.fail(
            "TEST_DATABASE_URL must target PostgreSQL cdms_test"
        )

    test_engine = create_engine(url)
    try:
        with test_engine.connect() as connection:
            try:
                connection.execute(
                    text("SELECT version_num FROM public.alembic_version")
                )
                connection.execute(
                    text("SELECT 1 FROM cdms.inbound_events LIMIT 0")
                )
            except Exception as exc:
                pytest.fail(
                    f"Run Alembic upgrade head on cdms_test first: {exc}"
                )

        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def db_client(engine):
    connection = engine.connect()
    outer = connection.begin()

    db = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            product_id = 1 + uuid.uuid4().int % 2_000_000_000
            yield db, client, product_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        outer.rollback()
        connection.close()


def send(client, product_id, version, name):
    response = client.post(
        "/v1/webhooks/products",
        json={
            "external_event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_SNAPSHOT",
            "source_version": version,
            "product": {
                "product_id": product_id,
                "sku": "SKU-201",
                "name": name,
                "is_active": True,
            },
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def state(db, client, product_id, result):
    event_id = uuid.UUID(result["event_id"])
    db.expire_all()

    event = db.get(InboundEvent, event_id)
    assert event.status != "FAILED", (
        event.error_code,
        event.error_message,
    )

    response = client.get(f"/v1/events/{event_id}")
    assert response.status_code == 200
    assert response.json()["status"] == event.status

    current = db.get(ProductCurrent, product_id)
    changes = (
        db.query(ProductChanges)
        .filter(ProductChanges.product_id == product_id)
        .order_by(ProductChanges.source_version)
        .all()
    )
    return event, current, changes


def test_new_product(db_client):
    db, client, product_id = db_client

    result = send(client, product_id, 1, "A")
    event, current, changes = state(
        db, client, product_id, result
    )

    assert event.status == "SUCCESS"
    assert (current.source_version, current.name) == (1, "A")
    assert len(changes) == 1
    assert changes[0].event_id == event.event_id
    assert current.last_change_id == changes[0].change_id


def test_stale(db_client):
    db, client, product_id = db_client

    send(client, product_id, 2, "B")
    result = send(client, product_id, 1, "A")
    event, current, changes = state(
        db, client, product_id, result
    )

    assert event.status == "STALE"
    assert (current.source_version, current.name) == (2, "B")
    assert len(changes) == 1


def test_duplicate(db_client):
    db, client, product_id = db_client

    send(client, product_id, 1, "A")
    result = send(client, product_id, 1, "A")
    event, current, changes = state(
        db, client, product_id, result
    )

    assert event.status == "DUPLICATE"
    assert current.source_version == 1
    assert len(changes) == 1


def test_conflict(db_client):
    db, client, product_id = db_client

    send(client, product_id, 1, "A")
    result = send(client, product_id, 1, "B")
    event, current, changes = state(
        db, client, product_id, result
    )

    assert event.status == "CONFLICT"
    assert current.name == "A"
    assert len(changes) == 1


def test_no_change(db_client):
    db, client, product_id = db_client

    send(client, product_id, 1, "A")
    current = db.get(ProductCurrent, product_id)
    old_change_id = current.last_change_id
    old_hash = current.business_hash

    result = send(client, product_id, 2, "A")
    event, current, changes = state(
        db, client, product_id, result
    )

    assert event.status == "NO_CHANGE"
    assert current.source_version == 2
    assert current.last_change_id == old_change_id
    assert current.business_hash == old_hash
    assert len(changes) == 1


def test_changed_and_changed_back(db_client):
    db, client, product_id = db_client

    send(client, product_id, 1, "A")

    result = send(client, product_id, 2, "B")
    event, current, changes = state(
        db, client, product_id, result
    )
    assert event.status == "SUCCESS"
    assert (current.source_version, current.name) == (2, "B")
    assert [change.source_version for change in changes] == [1, 2]
    assert current.last_change_id == changes[-1].change_id

    result = send(client, product_id, 3, "A")
    event, current, changes = state(
        db, client, product_id, result
    )
    assert event.status == "SUCCESS"
    assert current.name == "A"
    assert [change.source_version for change in changes] == [1, 2, 3]