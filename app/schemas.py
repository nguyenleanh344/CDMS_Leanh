from typing import Optional, List, Dict, Any, Literal
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
    
class WebhookProduct(BaseModel):
    product_id: int = Field(gt=0, strict=True)
    sku: str | None = Field(max_length=100, strict=True)
    name: str | None = Field(max_length=255, strict=True)
    is_active: StrictBool

    model_config = ConfigDict(extra="forbid")


class ProductWebhookPayload(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=128, strict=True)
    event_type: Literal["PRODUCT_SNAPSHOT"]
    source_version: int = Field(gt=0, strict=True)
    product: WebhookProduct

    model_config = ConfigDict(extra="forbid")
    
    
class SyncJobCreate(BaseModel):
    page_size: int = Field(default=100, ge=1, le=100, strict=True)
    max_products: int = Field(default=1000, ge=1, le=10000, strict=True)
    
    model_config= ConfigDict(extra="forbid")
    
class SyncJobResponse(BaseModel):
    job_id: str
    job_type:str
    status:str
    parameters: dict
    input_complete:bool
    attempt_count: int
    error_code:str|None
    error_message:str|None
    total_count:int
    success_count:int
    duplicate_count:int
    no_change_count:int
    stale_count:int
    conflict_count:int
    failed_count:int
    pending_count:int