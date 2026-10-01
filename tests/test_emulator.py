import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.db import Base, get_db
from app.models import EmulatorProduct

SQLALCHEMY_DATABASE_URL="sqlite:///:memory:"

engine=create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    execution_options={"schema_translate_map": {"emulator": None}},
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db=TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
    
@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine, tables=[EmulatorProduct.__table__])
    Base.metadata.create_all(bind=engine, tables=[EmulatorProduct.__table__])
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine, tables=[EmulatorProduct.__table__])

def test_create_product_success(client):
    response = client.post(
        "/v1/emulator/products",
        json={"sku": "TEST-SKU-01", "product_name": "Test Product", "is_active": True}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == "TEST-SKU-01"
    assert data["productName"] == "Test Product"
    assert data["isActive"] is True
    assert data["xCdmsVersion"] == 1
    assert "productId" in data
    
def test_reject_string_boolean(client):
    response = client.post(
        "/v1/emulator/products",
        json={"sku": "TEST-SKU-02", "product_name": "Test Fail", "is_active": "false"}
    )
    assert response.status_code == 422
    
def test_reject_extra_fields(client):
    response = client.post("/v1/emulator/products",
                           json={
                               "sku": "TEST-SKU-03",
                               "product_name": "Test Extra",
                               "is_active": True,
                               "extra_field": "should fail"
                           })
    assert response.status_code == 422
    
def test_pagination(client):
    product_ids = [
        client.post(
            "/v1/emulator/products",
            json={"sku": f"PAG-{i}", "product_name": f"P{i}", "is_active": True},
        ).json()["productId"]
        for i in range(1, 4)
    ]
    
    response = client.get("/v1/emulator/products?pageIndex=1&pageSize=2")
    assert response.status_code == 200
    data = response.json()
    
    assert "data" in data
    assert "pagination" in data
    assert data["pagination"]["pageIndex"] == 1
    assert data["pagination"]["pageSize"] == 2
    assert data["pagination"]["totalCount"] == 3
    assert [item["productId"] for item in data["data"]] == product_ids[:2]

    second_page = client.get("/v1/emulator/products?pageIndex=2&pageSize=2")
    assert second_page.status_code == 200
    assert second_page.json()["pagination"]["totalCount"] == 3
    assert [item["productId"] for item in second_page.json()["data"]] == product_ids[2:]
    
def test_update_with_changes(client):
    create_res = client.post(
        "/v1/emulator/products",
        json={"sku": "UPD-CHANGE", "product_name": "Old name", "is_active": True}
    )
    
    product_id = create_res.json()["productId"]
    initial_version = create_res.json()["xCdmsVersion"]
    
    update_res = client.put(
        f"/v1/emulator/products/{product_id}",
        json={"product_name": "New Name Updated"}
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    
    assert updated_data["productId"] == product_id
    assert updated_data["productName"] == "New Name Updated"
    assert updated_data["xCdmsVersion"] == initial_version + 1
    
def test_update_without_changes(client):
    create_res = client.post(
        "/v1/emulator/products",
        json={"sku": "UPD-SAME", "product_name": "Same Name", "is_active": True}
    )
    product_id = create_res.json()["productId"]
    initial_version = create_res.json()["xCdmsVersion"]

    update_res = client.put(
        f"/v1/emulator/products/{product_id}",
        json={"sku": "UPD-SAME", "product_name": "Same Name", "is_active": True}
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    
    assert updated_data["xCdmsVersion"] == initial_version
    
def test_product_not_found(client):
    none_existed_id = 999999
    
    get_res = client.get(f"/v1/emulator/products/{none_existed_id}")
    assert get_res.status_code == 404
    
    put_res = client.put(
        f"/v1/emulator/products/{none_existed_id}",
        json={"product_name": "Ghost Product"}
    )
    assert put_res.status_code == 404


def test_get_existing_product(client):
    created = client.post(
        "/v1/emulator/products",
        json={"sku": "GET-1", "product_name": "Existing", "is_active": True},
    ).json()

    response = client.get(f"/v1/emulator/products/{created['productId']}")
    assert response.status_code == 200
    assert response.json() == created


def test_update_is_active_increments_version(client):
    created = client.post(
        "/v1/emulator/products", json={"sku": "ACTIVE-1", "is_active": True}
    ).json()

    response = client.put(
        f"/v1/emulator/products/{created['productId']}", json={"is_active": False}
    )
    assert response.status_code == 200
    assert response.json()["isActive"] is False
    assert response.json()["xCdmsVersion"] == created["xCdmsVersion"] + 1


def test_update_rejects_string_boolean(client):
    created = client.post(
        "/v1/emulator/products", json={"sku": "ACTIVE-2", "is_active": True}
    ).json()

    response = client.put(
        f"/v1/emulator/products/{created['productId']}", json={"is_active": "false"}
    )
    assert response.status_code == 422
    assert client.get(f"/v1/emulator/products/{created['productId']}").json() == created


@pytest.mark.parametrize(
    "payload",
    [
        {"sku": "x" * 101, "is_active": True},
        {"product_name": "x" * 256, "is_active": True},
        {"sku": "MISSING-ACTIVE"},
        {"is_active": None},
        {"is_active": 1},
        {"sku": ["invalid"], "is_active": True},
    ],
)
def test_create_rejects_invalid_payload(client, payload):
    response = client.post("/v1/emulator/products", json=payload)
    assert response.status_code == 422
    assert client.get("/v1/emulator/products").json()["pagination"]["totalCount"] == 0
