from datetime import UTC, datetime
from decimal import Decimal

import pytest

from haley.domain import (
    ExecutionEventType,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
)
from haley.state_store import StateStore, StateStoreConstraintError


def make_intent(
    client_order_key: str = "client-1",
    exchange_identifier: str | None = "identifier-1",
) -> OrderIntent:
    return OrderIntent(
        client_order_key=client_order_key,
        exchange_identifier=exchange_identifier,
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        created_at=datetime.now(UTC),
        request_hash="request-hash",
    )


def test_saves_order_intent_before_submission() -> None:
    store = StateStore.in_memory()
    order_id = store.create_order(make_intent())

    saved = store.get_order(order_id)

    assert saved.order_id == order_id
    assert saved.status is OrderStatus.PLANNED
    assert saved.intent.client_order_key == "client-1"
    assert saved.intent.exchange_identifier == "identifier-1"


def test_exchange_identifier_is_globally_unique_when_present() -> None:
    store = StateStore.in_memory()
    store.create_order(make_intent(client_order_key="client-1", exchange_identifier="same"))

    with pytest.raises(StateStoreConstraintError, match="exchange_identifier"):
        store.create_order(make_intent(client_order_key="client-2", exchange_identifier="same"))


def test_active_client_order_key_cannot_be_reused() -> None:
    store = StateStore.in_memory()
    store.create_order(make_intent(client_order_key="client-1", exchange_identifier="id-1"))

    with pytest.raises(StateStoreConstraintError, match="client_order_key"):
        store.create_order(make_intent(client_order_key="client-1", exchange_identifier="id-2"))


def test_transition_appends_execution_event_and_increments_version() -> None:
    store = StateStore.in_memory()
    order_id = store.create_order(make_intent())

    updated = store.transition_order(
        order_id=order_id,
        next_status=OrderStatus.SUBMITTING,
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="paper submit",
    )
    events = store.list_execution_events(order_id)

    assert updated.status is OrderStatus.SUBMITTING
    assert updated.version == 2
    assert len(events) == 2
    assert events[-1].event_type is ExecutionEventType.ORDER_TRANSITION
    assert events[-1].payload == {"from": "PLANNED", "to": "SUBMITTING"}
    assert events[-1].operator_id == "local-user"


def test_invalid_transition_is_rejected_without_event_append() -> None:
    store = StateStore.in_memory()
    order_id = store.create_order(make_intent())

    with pytest.raises(ValueError, match="invalid order transition"):
        store.transition_order(
            order_id=order_id,
            next_status=OrderStatus.FILLED,
            request_id="req-1",
            idempotency_key="idem-1",
            operator_id="local-user",
            reason="skip unsafe states",
        )

    assert store.get_order(order_id).status is OrderStatus.PLANNED
    assert len(store.list_execution_events(order_id)) == 1
