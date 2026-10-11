from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List
from app.schemas import QuoteRequest, QuoteResponse
from app.pricing import quote_total

router = APIRouter()


@router.post("/orders/quote", response_model=QuoteResponse, include_in_schema=False)
@router.post("/quote", response_model=QuoteResponse)
async def get_order_quote(quote_request: QuoteRequest) -> QuoteResponse:
    """返回金额报价；兼容原有重复前缀路径。"""
    return QuoteResponse(total_amount=quote_total(quote_request.items), items=quote_request.items)
