import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import InboundEvent, ProductChanges, ProductCurrent


def business_hash(product: dict) -> str:
    fields = {
        key: product[key]
        for key in ("sku", "name", "is_active")
    }
    encoded = json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def outcome(
    current: ProductCurrent | None,
    version: int,
    new_hash: str,
) -> str:
    if current is None:
        return "SUCCESS"

    if version < current.source_version:
        return "STALE"

    if version == current.source_version:
        return (
            "DUPLICATE"
            if new_hash == current.business_hash
            else "CONFLICT"
        )

    return (
        "NO_CHANGE"
        if new_hash == current.business_hash
        else "SUCCESS"
    )


class ProductProcessor:
    @staticmethod
    def process(db: Session, event_id: uuid.UUID) -> str:
        try:
            event = db.get(
                InboundEvent,
                event_id,
                with_for_update=True,
            )
            if event is None:
                raise ValueError(f"Event {event_id} does not exist")

            if event.status not in ("RECEIVED", "RETRYING"):
                return event.status

            
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    ":namespace, :product_id)"
                ),
                {
                    "namespace": 1128549715,
                    "product_id": event.product_id,
                },
            )

            current = (
                db.query(ProductCurrent)
                .filter(ProductCurrent.product_id == event.product_id)
                .with_for_update()
                .one_or_none()
            )

            product = event.payload
            new_hash = business_hash(product)
            result = outcome(
                current,
                event.source_version,
                new_hash,
            )
            now = datetime.now(timezone.utc)

            if result == "SUCCESS":
                change_id = uuid.uuid4()

                db.add(
                    ProductChanges(
                        change_id=change_id,
                        product_id=event.product_id,
                        source_version=event.source_version,
                        event_id=event.event_id,
                        payload=product,
                        business_hash=new_hash,
                    )
                )

                if current is None:
                    db.add(
                        ProductCurrent(
                            product_id=event.product_id,
                            sku=product["sku"],
                            name=product["name"],
                            is_active=product["is_active"],
                            source_version=event.source_version,
                            business_hash=new_hash,
                            last_change_id=change_id,
                            observed_at=now,
                        )
                    )
                else:
                    current.sku = product["sku"]
                    current.name = product["name"]
                    current.is_active = product["is_active"]
                    current.source_version = event.source_version
                    current.business_hash = new_hash
                    current.last_change_id = change_id
                    current.observed_at = now

            elif result == "NO_CHANGE":
                current.source_version = event.source_version
                current.observed_at = now

            event.business_hash = new_hash
            event.status = result
            event.attempt_count += 1
            event.processed_at = now

            db.commit()
            return result

        except Exception as exc:
            db.rollback()

            failed_event = db.get(
                InboundEvent,
                event_id,
                with_for_update=True,
            )
            if failed_event is None:
                raise

            failed_event.status = "FAILED"
            failed_event.attempt_count += 1
            failed_event.error_code = type(exc).__name__
            failed_event.error_message = str(exc)[:1000]
            failed_event.processed_at = datetime.now(timezone.utc)
            db.commit()
            return "FAILED"