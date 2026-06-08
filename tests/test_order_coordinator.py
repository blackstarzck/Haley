from decimal import Decimal

import pytest

from haley.api_contracts import StateChangeRequest
from haley.domain import OrderSide, OrderStatus, OrderType
from haley.orders import DuplicateMarketOrderError, OrderCoordinator
from haley.state_store import StateStore


def make_state_change() -> StateChangeRequest:
    return StateChangeRequest(
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="paper order",
    )


def test_order_coordinator_creates_planned_limit_bid_order() -> None:
    store = StateStore.in_memory()
    coordinator = OrderCoordinator(store)

    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier="upbit-identifier-1",
        state_change=make_state_change(),
    )

    saved = store.get_order(order.order_id)
    assert saved.status is OrderStatus.PLANNED
    assert saved.intent.client_order_key != "upbit-identifier-1"
    assert saved.intent.exchange_identifier == "upbit-identifier-1"
    assert saved.intent.request_hash is not None


@pytest.mark.parametrize(
    "blocking_status",
    [
        OrderStatus.SUBMITTING,
        OrderStatus.UNKNOWN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_FAILED,
    ],
)
def test_order_coordinator_blocks_same_market_when_unsettled_order_exists(
    blocking_status: OrderStatus,
) -> None:
    store = StateStore.in_memory()
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier="upbit-identifier-1",
        state_change=make_state_change(),
    )
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.SUBMITTING,
        request_id="req-submit",
        idempotency_key="idem-submit",
        operator_id="local-user",
        reason="submit",
    )
    if blocking_status is OrderStatus.UNKNOWN:
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.UNKNOWN,
            request_id="req-timeout",
            idempotency_key="idem-timeout",
            operator_id="local-user",
            reason="timeout",
        )
    elif blocking_status is OrderStatus.PARTIALLY_FILLED:
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.ACCEPTED,
            request_id="req-accepted",
            idempotency_key="idem-accepted",
            operator_id="local-user",
            reason="accepted",
        )
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.PARTIALLY_FILLED,
            request_id="req-partial",
            idempotency_key="idem-partial",
            operator_id="local-user",
            reason="partial fill",
        )
    elif blocking_status is OrderStatus.CANCEL_FAILED:
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.ACCEPTED,
            request_id="req-accepted",
            idempotency_key="idem-accepted",
            operator_id="local-user",
            reason="accepted",
        )
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.CANCEL_REQUESTED,
            request_id="req-cancel",
            idempotency_key="idem-cancel",
            operator_id="local-user",
            reason="cancel requested",
        )
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.CANCEL_FAILED,
            request_id="req-cancel-failed",
            idempotency_key="idem-cancel-failed",
            operator_id="local-user",
            reason="cancel failed",
        )

    with pytest.raises(DuplicateMarketOrderError, match="KRW-XRP"):
        coordinator.create_entry_order(
            market="KRW-XRP",
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            quote_amount=Decimal("5000"),
            volume=Decimal("10"),
            limit_price=Decimal("500"),
            exchange_identifier="upbit-identifier-2",
            state_change=make_state_change(),
        )


def test_order_coordinator_records_timeout_as_unknown() -> None:
    store = StateStore.in_memory()
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier="upbit-identifier-1",
        state_change=make_state_change(),
    )
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.SUBMITTING,
        request_id="req-submit",
        idempotency_key="idem-submit",
        operator_id="local-user",
        reason="submit",
    )

    updated = coordinator.record_submit_timeout(
        order_id=order.order_id,
        state_change=StateChangeRequest(
            request_id="req-timeout",
            idempotency_key="idem-timeout",
            operator_id="local-user",
            reason="exchange response timeout",
        ),
    )

    assert updated.status is OrderStatus.UNKNOWN
