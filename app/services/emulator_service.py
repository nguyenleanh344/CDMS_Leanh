from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from app.models import EmulatorProduct
from app.schemas import ProductCreateRequest

class EmulatorService:
    @staticmethod
    def create_product(db: Session, payload: ProductCreateRequest) -> EmulatorProduct:
        try:
            db_product = EmulatorProduct(
                sku=payload.sku,
                product_name=payload.product_name,
                is_active=payload.is_active,
                source_version=1
            )
            db.add(db_product)
            db.commit()
            db.refresh(db_product)
            return db_product
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error occurred during product creation."
            )
    
    @staticmethod
    def list_products(db:Session, page_index: int = 1, page_size: int = 20):
        offset = (page_index - 1) * page_size
        query = db.query(EmulatorProduct)
        total_count = query.count()
        products = query.offset(offset).limit(page_size).all()
        return products, total_count