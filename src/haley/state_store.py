from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from haley.domain import (
    ExecutionEvent,
    ExecutionEventType,
    OrderIntent,
    OrderSide,
    OrderState,
    OrderStatus,
    OrderType,
)


class StateStoreConstraintError(RuntimeError):
    """Raised when a database safety constraint blocks a state write."""


class StateStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    @classmethod
    def in_memory(cls) -> StateStore:
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open(cls, path: str | Path) -> StateStore:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(db_path))

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

    def transition_order(
        self,
        order_id: str,
        next_status: OrderStatus,
        request_id: str,
        idempotency_key: str,
        operator_id: str,
        reason: str,
    ) -> OrderState:
        current = self.get_order(order_id)
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

    def list_execution_events(self, order_id: str) -> list[ExecutionEvent]:
        rows = self._connection.execute(
            """
            SELECT * FROM execution_events
            WHERE order_id = ?
            ORDER BY seq ASC
            """,
            (order_id,),
        ).fetchall()
        return [_row_to_execution_event(row) for row in rows]

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


def _constraint_message(exc: sqlite3.IntegrityError) -> str:
    text = str(exc)
    if "orders.exchange_identifier" in text:
        return "exchange_identifier must be globally unique"
    if "orders.client_order_key" in text:
        return "client_order_key is already active"
    return text
