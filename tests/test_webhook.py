from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app


@pytest.fixture
def client_and_db():
    db = MagicMock()

    db.query.return_value.filter.return_value.first.side_effect = (
        lambda: db.add.call_args.args[0] if db.add.called else None
    )

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def payload():
    return {
        "external_event_id": "product-101-v1",
        "event_type": "PRODUCT_SNAPSHOT",
        "source_version": 1,
        "product": {
            "product_id": 101,
            "sku": "SKU-001",
            "name": "Product A",
            "is_active": True,
        },
    }


def test_receive_webhook_success_and_get_event(client_and_db, payload):
    client, db = client_and_db

    response = client.post("/v1/webhooks/products", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ACCEPTED"
    assert data["replayed"] is False
    assert data["external_event_id"] == payload["external_event_id"]

    db.add.assert_called_once()
    db.commit.assert_called_once()

    stored_event = db.add.call_args.args[0]
    assert stored_event.product_id == 101
    assert stored_event.source_version == 1
    assert stored_event.payload == payload["product"]
    assert stored_event.raw_payload == payload

    get_response = client.get(f"/v1/events/{data['event_id']}")

    assert get_response.status_code == 200
    assert get_response.json()["event_id"] == data["event_id"]
    assert get_response.json()["external_event_id"] == payload["external_event_id"]
    assert get_response.json()["status"] == "RECEIVED"


def test_receive_webhook_replayed_idempotency(client_and_db, payload):
    client, db = client_and_db

    first_response = client.post("/v1/webhooks/products", json=payload)
    second_response = client.post("/v1/webhooks/products", json=payload)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert second_response.json()["status"] == "REPLAYED"
    assert second_response.json()["replayed"] is True
    assert second_response.json()["event_id"] == first_response.json()["event_id"]

    # Replay không tạo thêm event.
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_receive_webhook_conflict(client_and_db, payload):
    client, db = client_and_db

    first_response = client.post("/v1/webhooks/products", json=payload)
    assert first_response.status_code == 202

    changed_payload = {
        **payload,
        "product": {
            **payload["product"],
            "name": "Product A Modified",
        },
    }
    second_response = client.post(
        "/v1/webhooks/products",
        json=changed_payload,
    )

    assert second_response.status_code == 409
    assert "Idempotency conflict" in second_response.json()["detail"]

    # Request bị conflict không tạo thêm event.
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "changes",
    [
        {"external_event_id": ""},
        {"external_event_id": "x" * 129},
        {"event_type": "OTHER_EVENT"},
        {"source_version": 0},
        {"source_version": "1"},
        {"product": None},
        {"product": {"product_id": 0, "is_active": True}},
        {"product": {"product_id": 101, "is_active": "false"}},
        {"product": {"product_id": 101, "is_active": True, "extra": 1}},
        {"extra": 1},
    ],
)
def test_reject_invalid_webhook_payload(client_and_db, payload, changes):
    client, db = client_and_db

    response = client.post(
        "/v1/webhooks/products",
        json={**payload, **changes},
    )

    assert response.status_code == 422
    db.query.assert_not_called()
    db.add.assert_not_called()