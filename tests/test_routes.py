import pytest
from fastapi.testclient import TestClient
from decimal import Decimal
from app.main import app
from app.schemas import Item, QuoteRequest

client = TestClient(app)


def test_get_order_quote():
    # 准备数据
    items = [
        Item(unit_price=Decimal('10.5'), quantity=2),
        Item(unit_price=Decimal('20.3'), quantity=3)
    ]
    quote_request = QuoteRequest(items=items)

    # 发起请求
    response = client.post("/orders/quote", json=quote_request.model_dump())

    # 验证响应
    assert response.status_code == 200, "报价请求失败"
    data = response.json()
    expected_total = sum(item.unit_price * item.quantity for item in items)
    assert data["total_amount"] == str(expected_total), "计算的总价不正确"
