from datetime import UTC, datetime
from decimal import Decimal
import sqlite3
from threading import Event, Thread
import time

import pytest

from haley.domain import (
    ExecutionEventType,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskBlock,
    RiskBlockReason,
)
from haley.state_store import StateStore, StateStoreConstraintError


class ConcurrentUseDetectingConnection(sqlite3.Connection):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._active_risk_block_operation = False
        self._risk_block_select_entered = Event()

    @property
    def risk_block_select_entered(self) -> Event:
        return self._risk_block_select_entered

    def execute(self, sql: str, parameters: object = (), /) -> sqlite3.Cursor:
        normalized = " ".join(sql.lower().split())
        should_guard = "risk_blocks" in normalized
        if not should_guard:
            return super().execute(sql, parameters)

        if self._active_risk_block_operation:
            raise AssertionError("sqlite connection was used concurrently")
        self._active_risk_block_operation = True
        try:
            if normalized.startswith("select") and "from risk_blocks" in normalized:
                self._risk_block_select_entered.set()
                time.sleep(0.05)
            return super().execute(sql, parameters)
        finally:
            self._active_risk_block_operation = False


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


def test_execution_events_are_append_only_at_database_level() -> None:
    store = StateStore.in_memory()
    order_id = store.create_order(make_intent())
    event = store.list_execution_events(order_id)[0]

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store._connection.execute(  # noqa: SLF001 - verifies database contract.
            "UPDATE execution_events SET reason = ? WHERE event_id = ?",
            ("mutated", event.event_id),
        )

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        store._connection.execute(  # noqa: SLF001 - verifies database contract.
            "DELETE FROM execution_events WHERE event_id = ?",
            (event.event_id,),
        )


def test_stale_order_version_cannot_transition() -> None:
    store = StateStore.in_memory()
    order_id = store.create_order(make_intent())
    store.transition_order(
        order_id=order_id,
        next_status=OrderStatus.SUBMITTING,
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="paper submit",
    )

    with pytest.raises(StateStoreConstraintError, match="order version conflict"):
        store.transition_order(
            order_id=order_id,
            next_status=OrderStatus.UNKNOWN,
            request_id="req-2",
            idempotency_key="idem-2",
            operator_id="local-user",
            reason="stale transition",
            expected_version=1,
        )


def test_risk_block_reads_and_writes_are_serialized_on_shared_connection() -> None:
    connection = sqlite3.connect(
        ":memory:",
        check_same_thread=False,
        factory=ConcurrentUseDetectingConnection,
    )
    store = StateStore(connection)
    errors: list[BaseException] = []

    def list_blocks() -> None:
        try:
            store.list_risk_blocks()
        except BaseException as exc:  # pragma: no cover - reported below.
            errors.append(exc)

    thread = Thread(target=list_blocks)
    thread.start()
    assert connection.risk_block_select_entered.wait(timeout=1)

    try:
        store.record_risk_block(
            RiskBlock(
                reason=RiskBlockReason.DATA_STALE,
                market="KRW-XRP",
                detail="Market data is stale.",
            )
        )
    except BaseException as exc:  # pragma: no cover - reported below.
        errors.append(exc)

    thread.join(timeout=1)

    assert not thread.is_alive()
    assert errors == []
    assert len(store.list_risk_blocks()) == 1
