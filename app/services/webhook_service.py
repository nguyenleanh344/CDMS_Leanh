import hashlib
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InboundEvent
from app.schemas import ProductWebhookPayload
from app.services.product_processor import ProductProcessor


def request_fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class WebhookService:
    @staticmethod
    def receive(db: Session, data: ProductWebhookPayload) -> dict:
        raw = data.model_dump()
        fingerprint = request_fingerprint(raw)

        existing = (
            db.query(InboundEvent)
            .filter(
                InboundEvent.channel == "WEBHOOK",
                InboundEvent.external_event_id
                == data.external_event_id,
            )
            .first()
        )

        if existing is not None:
            return WebhookService._replay_or_conflict(
                existing,
                fingerprint,
            )

        event = InboundEvent(
            event_id=uuid.uuid4(),
            channel="WEBHOOK",
            external_event_id=data.external_event_id,
            product_id=data.product.product_id,
            source_version=data.source_version,
            raw_payload=raw,
            payload=raw["product"],
            request_fingerprint=fingerprint,
            status="RECEIVED",
            attempt_count=0,
        )

        try:
            db.add(event)
            db.commit()
        except IntegrityError:
            db.rollback()

            
            existing = (
                db.query(InboundEvent)
                .filter(
                    InboundEvent.channel == "WEBHOOK",
                    InboundEvent.external_event_id
                    == data.external_event_id,
                )
                .first()
            )
            if existing is not None:
                return WebhookService._replay_or_conflict(
                    existing,
                    fingerprint,
                )
            raise

        ProductProcessor.process(db, event.event_id)

        return {
            "status": "ACCEPTED",
            "replayed": False,
            "event_id": str(event.event_id),
            "external_event_id": event.external_event_id,
        }

    @staticmethod
    def _replay_or_conflict(
        event: InboundEvent,
        fingerprint: str,
    ) -> dict:
        if event.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Idempotency conflict: external_event_id "
                    "exists with a different payload fingerprint."
                ),
            )

        return {
            "status": "REPLAYED",
            "replayed": True,
            "event_id": str(event.event_id),
            "external_event_id": event.external_event_id,
        }