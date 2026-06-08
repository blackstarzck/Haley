from decimal import Decimal

from haley.domain import OrderSide, OrderType
from haley.dry_run import DryRunOrderValidator


def test_dry_run_rejects_below_minimum_krw_order() -> None:
    validator = DryRunOrderValidator(min_quote_amount=Decimal("5000"))

    result = validator.validate(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("4999"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
    )

    assert result.valid is False
    assert result.reasons == ["MIN_QUOTE_AMOUNT"]
    assert result.would_call_real_order_api is False


def test_dry_run_accepts_valid_limit_order_without_real_api() -> None:
    validator = DryRunOrderValidator(min_quote_amount=Decimal("5000"))

    result = validator.validate(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
    )

    assert result.valid is True
    assert result.reasons == []
    assert result.would_call_real_order_api is False
