from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List
from app.schemas import QuoteRequest, Item

router = APIRouter()


@router.post("/orders/quote", response_model=QuoteRequest)
async def get_order_quote(quote_request: QuoteRequest) -> dict:
    # 计算总价
    total_amount = sum(item.unit_price * item.quantity for item in quote_request.items)

    return {
        "total_amount": total_amount,
        "items": quote_request.items
    }
