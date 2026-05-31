from datetime import UTC, datetime
from decimal import Decimal

from haley.audit_log import AuditLogger
from haley.domain import (
    Alert,
    AlertSeverity,
    DataQualityState,
    ExecutionEventType,
    Fill,
    OrderSide,
    PositionState,
    ReconciliationState,
    ReconciliationStatus,
    RiskBlock,
    RiskBlockReason,
)
from haley.state_store import StateStore


def test_save_and_list_fills_preserves_decimal_values() -> None:
    store = StateStore.in_memory()
    fill = Fill(
        fill_id="fill-1",
        order_id="order-1",
        market="KRW-XRP",
        side=OrderSide.BID,
        price=Decimal("500.1"),
        volume=Decimal("10.25"),
        fee=Decimal("2.5005"),
        filled_at=datetime.now(UTC),
    )

    store.save_fill(fill)

    saved = store.list_fills("order-1")[0]
    assert saved.price == Decimal("500.1")
    assert saved.volume == Decimal("10.25")
    assert saved.fee == Decimal("2.5005")


def test_upsert_position_replaces_market_position_snapshot() -> None:
    store = StateStore.in_memory()
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
        )
    )
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("12"),
            average_entry_price=Decimal("510"),
            stop_protected=True,
        )
    )

    positions = store.list_positions()

    assert len(positions) == 1
    assert positions[0].market == "KRW-XRP"
    assert positions[0].volume == Decimal("12")
    assert positions[0].average_entry_price == Decimal("510")
    assert positions[0].stop_protected


def test_record_and_list_risk_blocks() -> None:
    store = StateStore.in_memory()
    block = RiskBlock(
        reason=RiskBlockReason.DATA_STALE,
        market="KRW-XRP",
        detail="WebSocket stale timeout exceeded",
    )

    store.record_risk_block(block)

    saved = store.list_risk_blocks()[0]
    assert saved.reason is RiskBlockReason.DATA_STALE
    assert saved.market == "KRW-XRP"
    assert saved.detail == "WebSocket stale timeout exceeded"


def test_create_ack_and_list_alerts() -> None:
    store = StateStore.in_memory()
    alert = Alert(
        alert_id="alert-1",
        severity=AlertSeverity.CRITICAL,
        message="보호 없는 포지션이 있습니다.",
    )

    store.create_alert(alert)
    store.ack_alert("alert-1", acknowledged_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC))

    saved = store.list_alerts()[0]
    assert saved.alert_id == "alert-1"
    assert saved.severity is AlertSeverity.CRITICAL
    assert saved.acknowledged_at == datetime(2026, 5, 31, 0, 0, tzinfo=UTC)


def test_audit_logger_masks_sensitive_payload_values() -> None:
    store = StateStore.in_memory()
    logger = AuditLogger(store)

    logger.log(
        event_type=ExecutionEventType.ORDER_TRANSITION,
        payload={"secret_key": "hidden", "safe": "value"},
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="mask test",
    )

    event = store.list_execution_events()[0]
    assert event.payload == {"secret_key": "[REDACTED]", "safe": "value"}
    assert event.operator_id == "local-user"


def test_upsert_and_list_data_quality_states_by_market() -> None:
    store = StateStore.in_memory()
    store.upsert_data_quality_state(
        market="KRW-XRP",
        state=DataQualityState(stale=True, rest_ws_mismatch=False),
    )

    saved = store.list_data_quality_states()["KRW-XRP"]

    assert saved.stale
    assert not saved.rest_ws_mismatch
    assert not saved.allows_new_entry


def test_save_and_get_reconciliation_state() -> None:
    store = StateStore.in_memory()
    store.save_reconciliation_state(
        ReconciliationState(
            status=ReconciliationStatus.MISMATCHED,
            mismatch_count=2,
            last_checked_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        )
    )

    saved = store.get_reconciliation_state()

    assert saved.status is ReconciliationStatus.MISMATCHED
    assert saved.mismatch_count == 2
    assert saved.last_checked_at == datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
