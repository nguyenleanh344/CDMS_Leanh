from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from app.models import EmulatorProduct
from app.schemas import ProductCreateRequest, ProductUpdateResquest

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
        products = query.order_by(EmulatorProduct.product_id).offset(offset).limit(page_size).all()
        return products, total_count
    
    @staticmethod
    def get_product_by_id(db: Session, product_id: int) -> EmulatorProduct:
        product=db.query(EmulatorProduct).filter(EmulatorProduct.product_id==product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"product with id {product_id} not found"
            )
        return product
    
    @staticmethod
    def update_product(db: Session, product_id: int, payload: ProductUpdateResquest) -> EmulatorProduct:
        product = EmulatorService.get_product_by_id(db, product_id)
        
        has_changed = False
        
        if payload.sku is not None and payload.sku != product.sku:
            has_changed = True
            product.sku=payload.sku
            
        if payload.product_name is not None and payload.product_name != product.product_name:
            product.product_name = payload.product_name
            has_changed = True

        if payload.is_active is not None and payload.is_active != product.is_active:
            product.is_active = payload.is_active
            has_changed = True
            
        try:
            
            if has_changed:
                product.source_version+=1
            db.commit()
            db.refresh(product)
            return product
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database error occured during product update."
            )
