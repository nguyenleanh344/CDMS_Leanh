import httpx
import pytest

from app.clients.inventory_client import InventoryClient, InventoryError


@pytest.mark.parametrize("code,body", [
    (503, {"detail": "unavailable"}),
    (200, {"data": [{"productId": 1}], "pagination": {}}),
    (200, {"data": [], "pagination": {
        "pageIndex": 2, "pageSize": 2, "totalCount": 0,
    }}),
])
def test_rejects_bad_response(monkeypatch, code, body):
    original_client = httpx.Client

    def fake_client(**kwargs):
        return original_client(transport=httpx.MockTransport(
            lambda request: httpx.Response(code, json=body)
        ), **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)
    with pytest.raises(InventoryError):
        InventoryClient("http://inventory.test").fetch_page(1, 2)


def test_maps_nullable_snapshot_and_version(monkeypatch):
    original_client = httpx.Client

    def fake_client(**kwargs):
        assert kwargs["timeout"] == 10.0
        return original_client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "data": [{
                    "productId": 12, "sku": None, "productName": None,
                    "isActive": False, "xCdmsVersion": 3,
                }],
                "pagination": {"pageIndex": 1, "pageSize": 2, "totalCount": 1},
            })
        ), **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)
    page = InventoryClient("http://inventory.test").fetch_page(1, 2)
    assert page.data[0].xCdmsVersion == 3
    assert page.data[0].payload() == {
        "product_id": 12, "sku": None, "name": None, "is_active": False,
    }


def test_timeout_is_inventory_error(monkeypatch):
    original_client = httpx.Client

    def fake_client(**kwargs):
        def timeout(request):
            raise httpx.ReadTimeout("timed out", request=request)

        return original_client(transport=httpx.MockTransport(timeout), **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)
    with pytest.raises(InventoryError, match="timed out"):
        InventoryClient("http://inventory.test").fetch_page(1, 2)