from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas import ProductCreateRequest, ProductResponse, ProductListResponse, PaginationMeta
from app.services.emulator_service import EmulatorService

router = APIRouter(prefix="/v1/emulator", tags=["Emulator"])

@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_emulator_product(payload: ProductCreateRequest, db: Session = Depends(get_db)):
    product = EmulatorService.create_product(db, payload)
    return ProductResponse(
        productId=product.product_id,
        sku=product.sku,
        productName=product.product_name,
        isActive=product.is_active,
        xCdmsVersion=product.source_version
    )
    
@router.get("/products", response_model=ProductListResponse)
def list_emulator_products(
    pageIndex: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    products, total_count = EmulatorService.list_products(db, pageIndex, pageSize)
    data = [
        ProductResponse(
            productId=p.product_id,
            sku=p.sku,
            productName=p.product_name,
            isActive=p.is_active,
            xCdmsVersion=p.source_version
        )
        for p in products
    ]
    return ProductListResponse(
        data=data,
        pagination=PaginationMeta(
            pageIndex=pageIndex,
            pageSize=pageSize,
            totalCount=total_count
        )
    )