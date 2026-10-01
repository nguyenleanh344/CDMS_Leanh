import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import InboundEvent
from app.schemas import ProductWebhookPayload
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/v1", tags=["Webhooks"])


@router.post(
    "/webhooks/products",
    status_code=status.HTTP_202_ACCEPTED,
)
def receive_product_webhook(
    data: ProductWebhookPayload,
    db: Session = Depends(get_db),
):
    return WebhookService.receive(db, data)


@router.get("/events/{event_id}")
def get_inbound_event(
    event_id: str,
    db: Session = Depends(get_db),
):
    query = db.query(InboundEvent)

    try:
        parsed = uuid.UUID(event_id)
        event = query.filter(
            (InboundEvent.event_id == parsed)
            | (InboundEvent.external_event_id == event_id)
        ).first()
    except ValueError:
        event = query.filter(
            InboundEvent.external_event_id == event_id
        ).first()

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event '{event_id}' not found.",
        )

    return {
        "event_id": str(event.event_id),
        "external_event_id": event.external_event_id,
        "channel": event.channel,
        "status": event.status,
        "received_at": event.received_at,
    }