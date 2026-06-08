from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from haley.domain import OrderSide, OrderType


@dataclass(frozen=True)
class DryRunValidationResult:
    valid: bool
    reasons: list[str]
    would_call_real_order_api: bool = False


class DryRunOrderValidator:
    def __init__(self, min_quote_amount: Decimal = Decimal("5000")) -> None:
        self._min_quote_amount = min_quote_amount

    def validate(
        self,
        market: str,
        side: OrderSide,
        order_type: OrderType,
        quote_amount: Decimal | None,
        volume: Decimal | None,
        limit_price: Decimal | None,
    ) -> DryRunValidationResult:
        reasons: list[str] = []
        if not market.startswith("KRW-"):
            reasons.append("KRW_MARKET_REQUIRED")
        if side is not OrderSide.BID and side is not OrderSide.ASK:
            reasons.append("UNSUPPORTED_SIDE")
        if order_type is OrderType.LIMIT and limit_price is None:
            reasons.append("LIMIT_PRICE_REQUIRED")
        if quote_amount is None or quote_amount < self._min_quote_amount:
            reasons.append("MIN_QUOTE_AMOUNT")
        if volume is None or volume <= 0:
            reasons.append("VOLUME_REQUIRED")
        return DryRunValidationResult(
            valid=not reasons,
            reasons=reasons,
            would_call_real_order_api=False,
        )
