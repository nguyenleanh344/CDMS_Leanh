import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from faker import Faker

from app.core.db import SessionLocal
from app.schemas import ProductCreateRequest
from app.services.emulator_service import EmulatorService


def positive_int(value: str) -> int:
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("--count must be greater than 0")
    return count


def seed(count: int) -> int:
    faker = Faker()
    created = 0

    with SessionLocal() as db:
        for _ in range(count):
            payload = ProductCreateRequest(
                sku=f"SKU-{uuid.uuid4().hex[:16].upper()}",
                product_name=faker.catch_phrase()[:255],
                is_active=faker.boolean(chance_of_getting_true=80),
            )
            EmulatorService.create_product(db, payload)
            created += 1

    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed emulator.products with fake products"
    )
    parser.add_argument("--count", type=positive_int, required=True)
    args = parser.parse_args()

    created = seed(args.count)
    print(f"Created {created} products in emulator.products (source_version = 1).")


if __name__ == "__main__":
    main()