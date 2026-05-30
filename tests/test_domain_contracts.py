from datetime import UTC, datetime
from decimal import Decimal

import pytest

from haley.domain import (
    DataQualityState,
    ExecutionEvent,
    ExecutionEventType,
    ModeState,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    RuntimeMode,
    blocks_new_entry_statuses,
    is_order_transition_allowed,
)


def test_runtime_mode_defaults_to_paper_and_live_is_structural_only() -> None:
    mode = ModeState()

    assert mode.mode is RuntimeMode.PAPER
    assert RuntimeMode.LIVE in RuntimeMode
    assert not mode.live_trading_enabled


def test_order_intent_requires_decimal_money_and_quantity() -> None:
    intent = OrderIntent(
        client_order_key="client-1",
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        created_at=datetime.now(UTC),
    )

    assert intent.quote_amount == Decimal("5000")
    assert intent.volume == Decimal("10")
    assert intent.limit_price == Decimal("500")

    with pytest.raises(TypeError, match="quote_amount"):
        OrderIntent(
            client_order_key="client-2",
            market="KRW-XRP",
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            quote_amount=5000.0,
            volume=Decimal("10"),
            limit_price=Decimal("500"),
            created_at=datetime.now(UTC),
        )


def test_order_state_machine_allows_safe_forward_transitions() -> None:
    assert is_order_transition_allowed(OrderStatus.PLANNED, OrderStatus.SUBMITTING)
    assert is_order_transition_allowed(OrderStatus.SUBMITTING, OrderStatus.UNKNOWN)
    assert is_order_transition_allowed(OrderStatus.SUBMITTING, OrderStatus.ACCEPTED)
    assert is_order_transition_allowed(OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED)
    assert is_order_transition_allowed(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED)
    assert is_order_transition_allowed(OrderStatus.UNKNOWN, OrderStatus.RECONCILED)


def test_order_state_machine_rejects_unsafe_backwards_or_skipped_transitions() -> None:
    assert not is_order_transition_allowed(OrderStatus.PLANNED, OrderStatus.FILLED)
    assert not is_order_transition_allowed(OrderStatus.FILLED, OrderStatus.SUBMITTING)
    assert not is_order_transition_allowed(OrderStatus.CANCELLED, OrderStatus.ACCEPTED)


def test_unsettled_order_statuses_block_same_market_new_entry() -> None:
    assert blocks_new_entry_statuses() == {
        OrderStatus.SUBMITTING,
        OrderStatus.UNKNOWN,
        OrderStatus.PARTIALLY_FILLED,
    }


def test_execution_events_are_append_only_records_with_operator_context() -> None:
    event = ExecutionEvent(
        event_id="evt-1",
        order_id="order-1",
        event_type=ExecutionEventType.ORDER_TRANSITION,
        occurred_at=datetime.now(UTC),
        payload={"from": "PLANNED", "to": "SUBMITTING"},
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="submit paper order",
    )

    assert event.payload["to"] == "SUBMITTING"
    assert event.operator_id == "local-user"


def test_data_quality_state_blocks_when_stale_or_mismatched() -> None:
    healthy = DataQualityState(stale=False, rest_ws_mismatch=False)
    stale = DataQualityState(stale=True, rest_ws_mismatch=False)
    mismatched = DataQualityState(stale=False, rest_ws_mismatch=True)

    assert healthy.allows_new_entry
    assert not stale.allows_new_entry
    assert not mismatched.allows_new_entry
