"""统一的 Decimal 金额计算。"""
from decimal import Decimal
from collections.abc import Sequence
from app.schemas import Item


def quote_total(items: Sequence[Item]) -> Decimal:
    """计算条目总金额，空列表返回 Decimal 零。"""
    return sum((item.unit_price * item.quantity for item in items), start=Decimal("0"))
