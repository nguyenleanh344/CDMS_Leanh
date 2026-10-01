from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, StrictBool

class ProductCreateRequest(BaseModel):
    sku: Optional[str] = Field(default=None, max_length=100)
    product_name: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(strict=True)
    
    model_config = ConfigDict(extra="forbid")
    
class ProductResponse(BaseModel):
    productId: int
    sku: Optional[str] = None
    productName: Optional[str] = None
    isActive: bool
    xCdmsVersion: int
    
    model_config = ConfigDict(from_attributes=True)
    
class PaginationMeta(BaseModel):
    pageIndex: int
    pageSize: int
    totalCount: int
    
class ProductListResponse(BaseModel):
    data: List[ProductResponse]
    pagination: PaginationMeta
    
class ProductUpdateResquest(BaseModel):
    sku: Optional[str] = Field(default=None, max_length=100)
    product_name: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[StrictBool] = None
    
    model_config = ConfigDict(extra="forbid") 