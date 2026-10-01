import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from app.core.config import settings

class InventoryError(Exception):
    pass

class InventoryProduct(BaseModel):
    productId: int = Field(gt=0, strict=True)
    sku: str | None = Field(max_length=100, strict=True)
    productName: str | None = Field(max_length=255, strict=True)
    isActive: StrictBool
    xCdmsVersion: int = Field(gt=0, strict=True)
    
    model_config = ConfigDict(extra="forbid")
    
    def payload(self) -> dict:
        return{
            "product_id": self.productId,
            "sku": self.sku,
            "name": self.productName,
            "is_active": self.isActive
        }
        
class InventoryPagination(BaseModel):
    pageIndex: int = Field(ge=1, strict=True)
    pageSize: int = Field(ge=1, le=100, strict=True)
    totalCount: int = Field(ge=0,strict=True)
    
    model_config = ConfigDict(extra="forbid")
    
class InventoryPage(BaseModel):
    data: list[InventoryProduct]
    pagination: InventoryPagination
    
    model_config = ConfigDict(extra = "forbid")
    
class InventoryClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.INVENTORY_BASE_URL).rstrip("/")
        
    def fetch_page(self, page_index: int, page_size: int) -> InventoryPage:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.base_url}/v1/emulator/products",
                    params={"pageIndex": page_index, "pageSize": page_size},
                )
                
                response.raise_for_status()
                page = InventoryPage.model_validate(response.json())
                
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise InventoryError(f"Emulator request failed: {exc}") from exc
        
        if page.pagination.pageIndex != page_index or page.pagination.pageSize != page_size:
            raise InventoryError("Emulator pagination does not match the request")
        if len(page.data) > page_size:
            raise InventoryError("Emulator returned too many products")
        if page.pagination.totalCount < len(page.data):
            raise InventoryError("Emulator totalCount is smaller than this page")
        return page
        