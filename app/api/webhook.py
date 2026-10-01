import uuid
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.db import get_db
from app.models import InboundEvent
from app.schemas import ProductWebhookPayload

router = APIRouter(prefix="/v1", tags=["Webhooks"])

def compute_fingerprint(data_dict: dict) -> str:
    # Tạo chuỗi JSON đồng nhất để sinh mã hash SHA-256 làm fingerprint
    json_str = json.dumps(data_dict, sort_keys=True)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

@router.post("/webhooks/products", status_code=status.HTTP_202_ACCEPTED)
def receive_product_webhook(data: ProductWebhookPayload, db: Session = Depends(get_db)):
    raw_data = data.model_dump()
    fingerprint = compute_fingerprint(raw_data)

    # 1. Kiểm tra xem external_event_id đã tồn tại hay chưa
    existing_event = db.query(InboundEvent).filter(
        InboundEvent.channel == "WEBHOOK",
        InboundEvent.external_event_id == data.external_event_id
    ).first()

    if existing_event:
        # Cùng external_event_id + cùng fingerprint -> Replayed request -> Trả về HTTP 200 (hoặc 202 kèm thông báo replayed)
        if existing_event.request_fingerprint == fingerprint:
            return {
                "status": "REPLAYED",
                "replayed": True,
                "event_id": str(existing_event.event_id),
                "external_event_id": existing_event.external_event_id
            }
        else:
            # Cùng external_event_id nhưng payload khác nhau -> Trả về HTTP 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency conflict: external_event_id exists with a different payload fingerprint."
            )

    try:
        # 2. Tạo bản ghi mới
        new_event = InboundEvent(
            event_id=uuid.uuid4(),
            channel="WEBHOOK",
            external_event_id=data.external_event_id,
            product_id=data.product.product_id,
            source_version=data.source_version,
            raw_payload=raw_data,
            payload=raw_data.get("product"),
            request_fingerprint=fingerprint,
            status="RECEIVED",
            attempt_count=0
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency conflict due to concurrent insert."
        )

    return {
        "status": "ACCEPTED",
        "replayed": False,
        "event_id": str(new_event.event_id),
        "external_event_id": new_event.external_event_id
    }


@router.get("/events/{event_id}")
def get_inbound_event(event_id: str, db: Session = Depends(get_db)):
    query = db.query(InboundEvent)
    
    try:
        uuid_obj = uuid.UUID(event_id)
        # Sửa lỗi điều kiện so sánh == thay vì !=
        event = query.filter(
            (InboundEvent.event_id == uuid_obj) | (InboundEvent.external_event_id == event_id)
        ).first()
    except ValueError:
        event = query.filter(InboundEvent.external_event_id == event_id).first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found."
        )
        
    return {
        "event_id": str(event.event_id),
        "external_event_id": event.external_event_id,
        "channel": event.channel,
        "status": event.status,
        "received_at": event.received_at
    }