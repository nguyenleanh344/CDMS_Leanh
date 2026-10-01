from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services import excel_import_service as excel


def workbook_bytes(rows=(), header=excel.HEADER, sheet="Products"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for row in rows:
        ws.append(row)
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def test_parses_rows_and_preserves_physical_row_numbers():
    rows = excel.parse_workbook(workbook_bytes([
        (101, "SKU-101", "A", True, 1),
        (102, None, None, "false", 2),
        (-3, "SKU-3", "Invalid", "yes", 1),
    ]))
    assert [r.item_index for r in rows] == [2, 3, 4]
    assert rows[0].payload == {
        "product_id": 101, "sku": "SKU-101", "name": "A", "is_active": True,
    }
    assert rows[1].payload == {
        "product_id": 102, "sku": None, "name": None, "is_active": False,
    }
    assert rows[2].payload is None
    assert rows[2].error_message and rows[2].product_id is None


@pytest.mark.parametrize("data", [
    b"not an xlsx workbook",
    workbook_bytes(sheet="Other"),
    workbook_bytes(header=("sku", "product_id", "name", "is_active", "source_version")),
    workbook_bytes(header=excel.HEADER + ("extra",)),
    workbook_bytes(header=excel.HEADER[:-1]),
])
def test_rejects_invalid_file_structure(data):
    with pytest.raises(HTTPException) as exc:
        excel.parse_workbook(data)
    assert exc.value.status_code == 422


def test_rejects_file_and_row_limits(monkeypatch):
    monkeypatch.setattr(excel, "MAX_FILE_BYTES", 10)
    with pytest.raises(HTTPException) as exc:
        excel.parse_workbook(workbook_bytes())
    assert exc.value.status_code == 413
    monkeypatch.setattr(excel, "MAX_FILE_BYTES", 5 * 1024 * 1024)
    monkeypatch.setattr(excel, "MAX_DATA_ROWS", 1)
    with pytest.raises(HTTPException) as exc:
        excel.parse_workbook(workbook_bytes([(1, None, None, True, 1)] * 2))
    assert exc.value.status_code == 413


def test_invalid_values_are_row_errors_and_raw_values_are_json_safe():
    row = excel._parse_row(2, (datetime(2026, 10, 1), Decimal("2.25"),
                               float("nan"), 1, Decimal("2")))
    assert row.payload is None and row.error_message
    assert row.raw_payload["product_id"] == "2026-10-01T00:00:00"
    assert row.raw_payload["sku"] == "2.25"
    assert row.raw_payload["name"] is None
    assert row.raw_payload["source_version"] == "2"


@pytest.mark.parametrize("active", [1, 0, "TRUE", "False", "yes", None])
def test_rejects_non_strict_booleans(active):
    row = excel._parse_row(2, (101, "A", "A", active, 1))
    assert row.payload is None and row.error_message