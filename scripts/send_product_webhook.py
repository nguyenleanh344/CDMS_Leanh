import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from pydantic import ValidationError

from app.clients.inventory_client import InventoryProduct
from app.core.config import settings
from app.schemas import ProductWebhookPayload

def positive_int(value: str) -> int:
    try:
        product_id = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("product id must be a positive number") from exc
    if product_id < 1:
        raise argparse.ArgumentTypeError("product id must be a positive integer") 
    return product_id
def send_product_webhook(
    product_id: int,
    emulator_base_url: str,
    cdms_base_url: str,
    client: httpx.Client | None = None,
) -> dict:
    if client is None:
        with httpx.Client(timeout=10.0) as owned_client:
            return send_product_webhook(
                product_id, emulator_base_url, cdms_base_url, owned_client
            )
    response = client.get(
        f"{emulator_base_url.rstrip('/')}/v1/emulator/products/{product_id}"
    )
    response.raise_for_status()
    product  = InventoryProduct.model_validate(response.json())
    if product.productId != product_id:
        raise ValueError("Emulator returned a different product_id")
    
    snapshot = ProductWebhookPayload.model_validate({
        "external_event_id": f"emulator-product-{product_id}-v{product.xCdmsVersion}",
        "event_type": "PRODUCT_SNAPSHOT",
        "source_version": product.xCdmsVersion,
        "product": product.payload(),
    })
    webhook_response = client.post(
        f"{cdms_base_url.rstrip('/')}/v1/webhooks/products",
        json=snapshot.model_dump(mode="json")
    )
    webhook_response.raise_for_status()
    return webhook_response.json()

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send an Emulator product snapshot to CDMS via webhook"
    )
    parser.add_argument("--product-id", type=positive_int, required=True)
    parser.add_argument(
        "--emulator-base-url", default=settings.INVENTORY_BASE_URL,
        help="Emulator API base URL (default: INVENTORY_BASE_URL)"
    )
    parser.add_argument(
        "--cdms-base-url", default="http://127.0.0.1:8000",
        help="CDMS API base URL"
    )
    args = parser.parse_args()
    try:
        result = send_product_webhook(
            args.product_id, args.emulator_base_url, args.cdms_base_url
        )
    except (httpx.HTTPError, ValueError, ValidationError) as exc:
        parser.exit(1, f'Webhook send failed {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
if __name__=="__main__":
    main()