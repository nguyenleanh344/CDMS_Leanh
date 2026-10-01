import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import ExcelImportAccepted, ExcelImportStatus, ExcelRowError
from app.services.excel_import_service import (
    MAX_FILE_BYTES,
    ExcelImportService,
    parse_workbook,
    process_excel_in_background,
)

router = APIRouter(prefix="/v1/imports", tags=["Imports"])


@router.post("/products", response_model=ExcelImportAccepted, status_code=202)
async def upload_products(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".xlsx") or not 1 <= len(filename) <= 255:
        raise HTTPException(422, "Upload a .xlsx file with a valid filename")
    try:
        contents = await file.read(MAX_FILE_BYTES + 1)
    finally:
        await file.close()
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(413, "Excel file exceeds 5 MiB")
    rows = parse_workbook(contents)
    job = ExcelImportService.create(db, filename, rows)
    accepted = ExcelImportService.accepted(job, len(rows))
    background_tasks.add_task(process_excel_in_background, job.job_id)
    return accepted


@router.get("/{batch_id}", response_model=ExcelImportStatus)
def get_import(batch_id: uuid.UUID, db: Session = Depends(get_db)):
    return ExcelImportService.response(db, ExcelImportService.get(db, batch_id))


@router.get("/{batch_id}/errors", response_model=list[ExcelRowError])
def get_import_errors(batch_id: uuid.UUID, db: Session = Depends(get_db)):
    return ExcelImportService.errors(db, ExcelImportService.get(db, batch_id))