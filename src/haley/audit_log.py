from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from haley.domain import ExecutionEvent, ExecutionEventType
from haley.security import mask_sensitive_values
from haley.state_store import StateStore


class AuditLogger:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    def log(
        self,
        event_type: ExecutionEventType,
        payload: dict[str, Any],
        request_id: str | None = None,
        idempotency_key: str | None = None,
        operator_id: str | None = None,
        reason: str | None = None,
        order_id: str | None = None,
    ) -> ExecutionEvent:
        event = ExecutionEvent(
            event_id=f"evt_{uuid4().hex}",
            order_id=order_id,
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            payload=mask_sensitive_values(payload),
            request_id=request_id,
            idempotency_key=idempotency_key,
            operator_id=operator_id,
            reason=reason,
        )
        self._store.append_execution_event(event)
        return event
