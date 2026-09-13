from pydantic import BaseModel, Field
from decimal import Decimal


# 商品条目模型
class Item(BaseModel):
    unit_price: Decimal = Field(..., description="商品单价")
    quantity: int = Field(..., description="商品数量")


# 报价请求模型
class QuoteRequest(BaseModel):
    items: list[Item] = Field(..., description="一组商品条目")