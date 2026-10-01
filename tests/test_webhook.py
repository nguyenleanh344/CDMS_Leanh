from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.services.product_processor import ProductProcessor


@pytest.fixture
def client_and_dependencies(monkeypatch):
    db = MagicMock()
    processor = MagicMock(return_value="SUCCESS")
    monkeypatch.setattr(ProductProcessor, "process", processor)


    db.query.return_value.filter.return_value.first.side_effect = (
        lambda: db.add.call_args.args[0] if db.add.called else None
    )

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, db, processor
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


def test_receive_webhook_success_and_get_event(
    client_and_dependencies,
    payload,
):
    client, db, processor = client_and_dependencies

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
    processor.assert_called_once_with(db, stored_event.event_id)

    get_response = client.get(f"/v1/events/{data['event_id']}")

    assert get_response.status_code == 200
    assert get_response.json()["event_id"] == data["event_id"]
    assert (
        get_response.json()["external_event_id"]
        == payload["external_event_id"]
    )

    assert get_response.json()["status"] == "RECEIVED"


def test_receive_webhook_replayed(
    client_and_dependencies,
    payload,
):
    client, db, processor = client_and_dependencies

    first = client.post("/v1/webhooks/products", json=payload)
    second = client.post("/v1/webhooks/products", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["status"] == "REPLAYED"
    assert second.json()["replayed"] is True
    assert second.json()["event_id"] == first.json()["event_id"]

    db.add.assert_called_once()
    db.commit.assert_called_once()
    processor.assert_called_once()


def test_receive_webhook_conflict(
    client_and_dependencies,
    payload,
):
    client, db, processor = client_and_dependencies

    first = client.post("/v1/webhooks/products", json=payload)
    assert first.status_code == 202

    changed = {
        **payload,
        "product": {
            **payload["product"],
            "name": "Product A Modified",
        },
    }
    response = client.post("/v1/webhooks/products", json=changed)

    assert response.status_code == 409
    assert "Idempotency conflict" in response.json()["detail"]

    db.add.assert_called_once()
    db.commit.assert_called_once()
    processor.assert_called_once()


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
        {
            "product": {
                "product_id": 101,
                "is_active": True,
                "extra": 1,
            }
        },
        {"extra": 1},
    ],
)
def test_reject_invalid_payload(
    client_and_dependencies,
    payload,
    changes,
):
    client, db, processor = client_and_dependencies

    response = client.post(
        "/v1/webhooks/products",
        json={**payload, **changes},
    )

    assert response.status_code == 422
    db.query.assert_not_called()
    db.add.assert_not_called()
    processor.assert_not_called()
    
def test_nullable_fields_must_be_present(client_and_dependencies, payload):
    client, db, processor = client_and_dependencies
    nullable = {
        **payload,
        "product": {
            **payload["product"],
            "sku": None,
            "name": None,
        },
    }

    response = client.post("/v1/webhooks/products", json=nullable)

    assert response.status_code == 202
    assert db.add.call_args.args[0].payload["sku"] is None
    assert db.add.call_args.args[0].payload["name"] is None
    processor.assert_called_once()