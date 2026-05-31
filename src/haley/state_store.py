from __future__ import annotations

import json
import sqlite3
from threading import RLock
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from haley.domain import (
    Alert,
    AlertSeverity,
    DataQualityState,
    ExecutionEvent,
    ExecutionEventType,
    Fill,
    OrderIntent,
    OrderSide,
    OrderState,
    OrderStatus,
    OrderType,
    PositionState,
    ReconciliationState,
    ReconciliationStatus,
    RiskBlock,
    RiskBlockReason,
    StopProtectionState,
)


class StateStoreConstraintError(RuntimeError):
    """Raised when a database safety constraint blocks a state write."""


class StateStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._initialize_schema()

    @classmethod
    def in_memory(cls) -> StateStore:
        return cls(sqlite3.connect(":memory:", check_same_thread=False))

    @classmethod
    def open(cls, path: str | Path) -> StateStore:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(db_path, check_same_thread=False))

    def create_order(self, intent: OrderIntent) -> str:
        order_id = f"order_{uuid4().hex}"
        now = _utc_now()
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO orders (
                        order_id,
                        client_order_key,
                        exchange_identifier,
                        market,
                        side,
                        order_type,
                        quote_amount,
                        volume,
                        limit_price,
                        request_hash,
                        created_at,
                        status,
                        version,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        intent.client_order_key,
                        intent.exchange_identifier,
                        intent.market,
                        intent.side.value,
                        intent.order_type.value,
                        _decimal_to_text(intent.quote_amount),
                        _decimal_to_text(intent.volume),
                        _decimal_to_text(intent.limit_price),
                        intent.request_hash,
                        intent.created_at.isoformat(),
                        OrderStatus.PLANNED.value,
                        1,
                        now.isoformat(),
                    ),
                )
                self._insert_execution_event(
                    ExecutionEvent(
                        event_id=f"evt_{uuid4().hex}",
                        order_id=order_id,
                        event_type=ExecutionEventType.ORDER_INTENT_CREATED,
                        occurred_at=now,
                        payload={"status": OrderStatus.PLANNED.value},
                    )
                )
        except sqlite3.IntegrityError as exc:
            raise StateStoreConstraintError(_constraint_message(exc)) from exc
        return order_id

    def get_order(self, order_id: str) -> OrderState:
        row = self._connection.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"order not found: {order_id}")
        return _row_to_order_state(row)

    def list_orders_for_market(
        self, market: str, statuses: set[OrderStatus] | None = None
    ) -> list[OrderState]:
        if statuses is None:
            rows = self._connection.execute(
                "SELECT * FROM orders WHERE market = ? ORDER BY created_at ASC",
                (market,),
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in statuses)
            rows = self._connection.execute(
                f"""
                SELECT * FROM orders
                WHERE market = ? AND status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                (market, *(status.value for status in statuses)),
            ).fetchall()
        return [_row_to_order_state(row) for row in rows]

    def list_orders(self) -> list[OrderState]:
        rows = self._connection.execute(
            "SELECT * FROM orders ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_order_state(row) for row in rows]

    def transition_order(
        self,
        order_id: str,
        next_status: OrderStatus,
        request_id: str,
        idempotency_key: str,
        operator_id: str,
        reason: str,
        expected_version: int | None = None,
    ) -> OrderState:
        current = self.get_order(order_id)
        if expected_version is not None and current.version != expected_version:
            raise StateStoreConstraintError("order version conflict")
        updated = current.transition_to(next_status)
        now = _utc_now()

        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE orders
                SET status = ?, version = ?, updated_at = ?
                WHERE order_id = ? AND version = ?
                """,
                (
                    updated.status.value,
                    updated.version,
                    now.isoformat(),
                    order_id,
                    current.version,
                ),
            )
            if cursor.rowcount != 1:
                raise StateStoreConstraintError("order version conflict")
            self._insert_execution_event(
                ExecutionEvent(
                    event_id=f"evt_{uuid4().hex}",
                    order_id=order_id,
                    event_type=ExecutionEventType.ORDER_TRANSITION,
                    occurred_at=now,
                    payload={
                        "from": current.status.value,
                        "to": updated.status.value,
                    },
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    operator_id=operator_id,
                    reason=reason,
                )
            )

        return self.get_order(order_id)

    def append_execution_event(self, event: ExecutionEvent) -> None:
        with self._connection:
            self._insert_execution_event(event)

    def list_execution_events(self, order_id: str | None = None) -> list[ExecutionEvent]:
        if order_id is None:
            rows = self._connection.execute(
                "SELECT * FROM execution_events ORDER BY seq ASC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT * FROM execution_events
                WHERE order_id = ?
                ORDER BY seq ASC
                """,
                (order_id,),
            ).fetchall()
        return [_row_to_execution_event(row) for row in rows]

    def save_fill(self, fill: Fill) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fills (
                    fill_id,
                    order_id,
                    market,
                    side,
                    price,
                    volume,
                    fee,
                    filled_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.fill_id,
                    fill.order_id,
                    fill.market,
                    fill.side.value,
                    _decimal_to_text(fill.price),
                    _decimal_to_text(fill.volume),
                    _decimal_to_text(fill.fee),
                    fill.filled_at.isoformat(),
                ),
            )

    def list_fills(self, order_id: str | None = None) -> list[Fill]:
        if order_id is None:
            rows = self._connection.execute("SELECT * FROM fills ORDER BY filled_at ASC").fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM fills WHERE order_id = ? ORDER BY filled_at ASC",
                (order_id,),
            ).fetchall()
        return [_row_to_fill(row) for row in rows]

    def upsert_position(self, position: PositionState) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO positions (
                    market,
                    volume,
                    average_entry_price,
                    realized_pnl,
                    stop_protected,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(market) DO UPDATE SET
                    volume = excluded.volume,
                    average_entry_price = excluded.average_entry_price,
                    realized_pnl = excluded.realized_pnl,
                    stop_protected = excluded.stop_protected,
                    updated_at = excluded.updated_at
                """,
                (
                    position.market,
                    _decimal_to_text(position.volume),
                    _decimal_to_text(position.average_entry_price),
                    _decimal_to_text(position.realized_pnl),
                    1 if position.stop_protected else 0,
                    position.updated_at.isoformat(),
                ),
            )

    def list_positions(self) -> list[PositionState]:
        rows = self._connection.execute(
            "SELECT * FROM positions ORDER BY market ASC"
        ).fetchall()
        return [_row_to_position(row) for row in rows]

    def create_stop_protection(self, state: StopProtectionState) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO stop_protections (
                    market,
                    position_volume,
                    protected,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    state.market,
                    _decimal_to_text(state.position_volume),
                    1 if state.protected else 0,
                    state.created_at.isoformat(),
                ),
            )

    def list_stop_protections(self, market: str | None = None) -> list[StopProtectionState]:
        if market is None:
            rows = self._connection.execute(
                "SELECT * FROM stop_protections ORDER BY seq ASC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM stop_protections WHERE market = ? ORDER BY seq ASC",
                (market,),
            ).fetchall()
        return [_row_to_stop_protection(row) for row in rows]

    def record_risk_block(self, block: RiskBlock) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO risk_blocks (reason, market, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    block.reason.value,
                    block.market,
                    block.detail,
                    block.created_at.isoformat(),
                ),
            )

    def list_risk_blocks(self) -> list[RiskBlock]:
        rows = self._connection.execute(
            "SELECT * FROM risk_blocks ORDER BY seq ASC"
        ).fetchall()
        return [_row_to_risk_block(row) for row in rows]

    def create_alert(self, alert: Alert) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO alerts (
                    alert_id,
                    severity,
                    message,
                    created_at,
                    acknowledged_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.severity.value,
                    alert.message,
                    alert.created_at.isoformat(),
                    None
                    if alert.acknowledged_at is None
                    else alert.acknowledged_at.isoformat(),
                ),
            )

    def ack_alert(self, alert_id: str, acknowledged_at: datetime | None = None) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE alerts SET acknowledged_at = ? WHERE alert_id = ?",
                ((_utc_now() if acknowledged_at is None else acknowledged_at).isoformat(), alert_id),
            )

    def list_alerts(self) -> list[Alert]:
        rows = self._connection.execute(
            "SELECT * FROM alerts ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def upsert_data_quality_state(self, market: str, state: DataQualityState) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO data_quality_states (
                    market,
                    stale,
                    rest_ws_mismatch,
                    market_warning,
                    orderbook_gap,
                    last_ws_received_at,
                    last_rest_sync_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market) DO UPDATE SET
                    stale = excluded.stale,
                    rest_ws_mismatch = excluded.rest_ws_mismatch,
                    market_warning = excluded.market_warning,
                    orderbook_gap = excluded.orderbook_gap,
                    last_ws_received_at = excluded.last_ws_received_at,
                    last_rest_sync_at = excluded.last_rest_sync_at
                """,
                (
                    market,
                    1 if state.stale else 0,
                    1 if state.rest_ws_mismatch else 0,
                    1 if state.market_warning else 0,
                    1 if state.orderbook_gap else 0,
                    None
                    if state.last_ws_received_at is None
                    else state.last_ws_received_at.isoformat(),
                    None
                    if state.last_rest_sync_at is None
                    else state.last_rest_sync_at.isoformat(),
                ),
            )

    def list_data_quality_states(self) -> dict[str, DataQualityState]:
        rows = self._connection.execute(
            "SELECT * FROM data_quality_states ORDER BY market ASC"
        ).fetchall()
        return {row["market"]: _row_to_data_quality_state(row) for row in rows}

    def save_reconciliation_state(self, state: ReconciliationState) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM reconciliation_state")
            self._connection.execute(
                """
                INSERT INTO reconciliation_state (
                    singleton_id,
                    status,
                    mismatch_count,
                    last_checked_at
                )
                VALUES (1, ?, ?, ?)
                """,
                (
                    state.status.value,
                    state.mismatch_count,
                    None
                    if state.last_checked_at is None
                    else state.last_checked_at.isoformat(),
                ),
            )

    def get_reconciliation_state(self) -> ReconciliationState:
        row = self._connection.execute(
            "SELECT * FROM reconciliation_state WHERE singleton_id = 1"
        ).fetchone()
        if row is None:
            return ReconciliationState()
        return _row_to_reconciliation_state(row)

    def save_paper_portfolio(self, portfolio: object) -> None:
        with self._lock:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO paper_portfolio (
                        singleton_id,
                        initial_cash_krw,
                        cash_krw,
                        locked_cash_krw
                    )
                    VALUES (1, ?, ?, ?)
                    ON CONFLICT(singleton_id) DO UPDATE SET
                        initial_cash_krw = excluded.initial_cash_krw,
                        cash_krw = excluded.cash_krw,
                        locked_cash_krw = excluded.locked_cash_krw
                    """,
                    (
                        _decimal_to_text(portfolio.initial_cash_krw),
                        _decimal_to_text(portfolio.cash_krw),
                        _decimal_to_text(portfolio.locked_cash_krw),
                    ),
                )

    def get_paper_portfolio(self) -> object:
        from haley.paper import PaperPortfolio

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM paper_portfolio WHERE singleton_id = 1"
            ).fetchone()
        if row is None:
            raise KeyError("paper portfolio not found")
        return PaperPortfolio(
            initial_cash_krw=Decimal(row["initial_cash_krw"]),
            cash_krw=Decimal(row["cash_krw"]),
            locked_cash_krw=Decimal(row["locked_cash_krw"]),
        )

    def _insert_execution_event(self, event: ExecutionEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO execution_events (
                event_id,
                order_id,
                event_type,
                occurred_at,
                payload_json,
                request_id,
                idempotency_key,
                operator_id,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.order_id,
                event.event_type.value,
                event.occurred_at.isoformat(),
                json.dumps(dict(event.payload), sort_keys=True),
                event.request_id,
                event.idempotency_key,
                event.operator_id,
                event.reason,
            ),
        )

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_key TEXT NOT NULL,
                    exchange_identifier TEXT UNIQUE,
                    market TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quote_amount TEXT,
                    volume TEXT,
                    limit_price TEXT,
                    request_hash TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_active_client_order_key
                ON orders(client_order_key)
                WHERE status IN (
                    'PLANNED',
                    'SUBMITTING',
                    'UNKNOWN',
                    'ACCEPTED',
                    'PARTIALLY_FILLED',
                    'CANCEL_REQUESTED',
                    'CANCEL_FAILED'
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    order_id TEXT,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    request_id TEXT,
                    idempotency_key TEXT,
                    operator_id TEXT,
                    reason TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(order_id)
                );

                CREATE TRIGGER IF NOT EXISTS prevent_execution_events_update
                BEFORE UPDATE ON execution_events
                BEGIN
                    SELECT RAISE(ABORT, 'execution_events is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS prevent_execution_events_delete
                BEFORE DELETE ON execution_events
                BEGIN
                    SELECT RAISE(ABORT, 'execution_events is append-only');
                END;

                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    filled_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    market TEXT PRIMARY KEY,
                    volume TEXT NOT NULL,
                    average_entry_price TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    stop_protected INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stop_protections (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT NOT NULL,
                    position_volume TEXT NOT NULL,
                    protected INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS risk_blocks (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    reason TEXT NOT NULL,
                    market TEXT,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT
                );

                CREATE TABLE IF NOT EXISTS data_quality_states (
                    market TEXT PRIMARY KEY,
                    stale INTEGER NOT NULL,
                    rest_ws_mismatch INTEGER NOT NULL,
                    market_warning INTEGER NOT NULL,
                    orderbook_gap INTEGER NOT NULL,
                    last_ws_received_at TEXT,
                    last_rest_sync_at TEXT
                );

                CREATE TABLE IF NOT EXISTS reconciliation_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    status TEXT NOT NULL,
                    mismatch_count INTEGER NOT NULL,
                    last_checked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS paper_portfolio (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    initial_cash_krw TEXT NOT NULL,
                    cash_krw TEXT NOT NULL,
                    locked_cash_krw TEXT NOT NULL
                );
                """
            )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _decimal_to_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal_from_text(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_order_state(row: sqlite3.Row) -> OrderState:
    intent = OrderIntent(
        client_order_key=row["client_order_key"],
        exchange_identifier=row["exchange_identifier"],
        market=row["market"],
        side=OrderSide(row["side"]),
        order_type=OrderType(row["order_type"]),
        quote_amount=_decimal_from_text(row["quote_amount"]),
        volume=_decimal_from_text(row["volume"]),
        limit_price=_decimal_from_text(row["limit_price"]),
        request_hash=row["request_hash"],
        created_at=_datetime_from_text(row["created_at"]),
    )
    return OrderState(
        order_id=row["order_id"],
        intent=intent,
        status=OrderStatus(row["status"]),
        version=row["version"],
        updated_at=_datetime_from_text(row["updated_at"]),
    )


def _row_to_execution_event(row: sqlite3.Row) -> ExecutionEvent:
    payload: dict[str, Any] = json.loads(row["payload_json"])
    return ExecutionEvent(
        event_id=row["event_id"],
        order_id=row["order_id"],
        event_type=ExecutionEventType(row["event_type"]),
        occurred_at=_datetime_from_text(row["occurred_at"]),
        payload=payload,
        request_id=row["request_id"],
        idempotency_key=row["idempotency_key"],
        operator_id=row["operator_id"],
        reason=row["reason"],
    )


def _row_to_fill(row: sqlite3.Row) -> Fill:
    return Fill(
        fill_id=row["fill_id"],
        order_id=row["order_id"],
        market=row["market"],
        side=OrderSide(row["side"]),
        price=Decimal(row["price"]),
        volume=Decimal(row["volume"]),
        fee=Decimal(row["fee"]),
        filled_at=_datetime_from_text(row["filled_at"]),
    )


def _row_to_position(row: sqlite3.Row) -> PositionState:
    return PositionState(
        market=row["market"],
        volume=Decimal(row["volume"]),
        average_entry_price=Decimal(row["average_entry_price"]),
        realized_pnl=Decimal(row["realized_pnl"]),
        stop_protected=bool(row["stop_protected"]),
        updated_at=_datetime_from_text(row["updated_at"]),
    )


def _row_to_stop_protection(row: sqlite3.Row) -> StopProtectionState:
    return StopProtectionState(
        market=row["market"],
        position_volume=Decimal(row["position_volume"]),
        protected=bool(row["protected"]),
        created_at=_datetime_from_text(row["created_at"]),
    )


def _row_to_risk_block(row: sqlite3.Row) -> RiskBlock:
    return RiskBlock(
        reason=RiskBlockReason(row["reason"]),
        market=row["market"],
        detail=row["detail"],
        created_at=_datetime_from_text(row["created_at"]),
    )


def _row_to_alert(row: sqlite3.Row) -> Alert:
    acknowledged_at = row["acknowledged_at"]
    return Alert(
        alert_id=row["alert_id"],
        severity=AlertSeverity(row["severity"]),
        message=row["message"],
        created_at=_datetime_from_text(row["created_at"]),
        acknowledged_at=None
        if acknowledged_at is None
        else _datetime_from_text(acknowledged_at),
    )


def _row_to_data_quality_state(row: sqlite3.Row) -> DataQualityState:
    last_ws_received_at = row["last_ws_received_at"]
    last_rest_sync_at = row["last_rest_sync_at"]
    return DataQualityState(
        stale=bool(row["stale"]),
        rest_ws_mismatch=bool(row["rest_ws_mismatch"]),
        market_warning=bool(row["market_warning"]),
        orderbook_gap=bool(row["orderbook_gap"]),
        last_ws_received_at=None
        if last_ws_received_at is None
        else _datetime_from_text(last_ws_received_at),
        last_rest_sync_at=None
        if last_rest_sync_at is None
        else _datetime_from_text(last_rest_sync_at),
    )


def _row_to_reconciliation_state(row: sqlite3.Row) -> ReconciliationState:
    last_checked_at = row["last_checked_at"]
    return ReconciliationState(
        status=ReconciliationStatus(row["status"]),
        mismatch_count=row["mismatch_count"],
        last_checked_at=None
        if last_checked_at is None
        else _datetime_from_text(last_checked_at),
    )


def _constraint_message(exc: sqlite3.IntegrityError) -> str:
    text = str(exc)
    if "orders.exchange_identifier" in text:
        return "exchange_identifier must be globally unique"
    if "orders.client_order_key" in text:
        return "client_order_key is already active"
    return text
