from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from haley.domain import ReconciliationState, ReconciliationStatus
from haley.security import REDACTED
from haley.state_store import StateStore


class RecoveryStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RecoveryStep:
    name: str
    status: RecoveryStepStatus
    detail: str


@dataclass(frozen=True)
class RecoveryRun:
    recovery_run_id: str
    status: RecoveryStepStatus
    reconciliation_status: ReconciliationStatus
    steps: list[RecoveryStep]


class RecoveryManager:
    def __init__(self, store: StateStore, exchange: object) -> None:
        self._store = store
        self._exchange = exchange

    def run(self) -> RecoveryRun:
        recovery_run_id = f"recovery_{uuid4().hex}"
        self._store.save_reconciliation_state(
            ReconciliationState(status=ReconciliationStatus.RUNNING)
        )
        steps: list[RecoveryStep] = []
        try:
            accounts = self._exchange.list_accounts()
        except Exception as exc:
            self._store.save_reconciliation_state(
                ReconciliationState(status=ReconciliationStatus.FAILED)
            )
            return RecoveryRun(
                recovery_run_id=recovery_run_id,
                status=RecoveryStepStatus.FAILED,
                reconciliation_status=ReconciliationStatus.FAILED,
                steps=[
                    RecoveryStep(
                        name="balance_lookup",
                        status=RecoveryStepStatus.FAILED,
                        detail=_redact_text(str(exc)),
                    )
                ],
            )

        steps.append(
            RecoveryStep(
                name="balance_lookup",
                status=RecoveryStepStatus.SUCCEEDED,
                detail=f"accounts={len(accounts)}",
            )
        )

        open_orders = self._exchange.list_open_orders()
        steps.append(
            RecoveryStep(
                name="open_orders_lookup",
                status=RecoveryStepStatus.SUCCEEDED,
                detail=f"open_orders={len(open_orders)}",
            )
        )

        mismatch_count = 0
        checked = 0
        for item in open_orders:
            identifier = item["identifier"]
            self._exchange.get_order_detail(identifier)
            checked += 1
            if not _local_exchange_identifier_exists(self._store, identifier):
                mismatch_count += 1

        steps.append(
            RecoveryStep(
                name="order_detail_reconciliation",
                status=RecoveryStepStatus.SUCCEEDED,
                detail=f"checked={checked}",
            )
        )

        reconciliation_status = (
            ReconciliationStatus.MATCHED
            if mismatch_count == 0
            else ReconciliationStatus.MISMATCHED
        )
        self._store.save_reconciliation_state(
            ReconciliationState(
                status=reconciliation_status,
                mismatch_count=mismatch_count,
                last_checked_at=datetime.now(UTC),
                operator_resume_required=reconciliation_status
                is ReconciliationStatus.MATCHED,
            )
        )
        return RecoveryRun(
            recovery_run_id=recovery_run_id,
            status=RecoveryStepStatus.SUCCEEDED
            if reconciliation_status is ReconciliationStatus.MATCHED
            else RecoveryStepStatus.FAILED,
            reconciliation_status=reconciliation_status,
            steps=steps,
        )


def _redact_text(value: str) -> str:
    lowered = value.lower()
    for marker in ("secret", "jwt", "nonce", "query_hash"):
        if marker in lowered:
            return REDACTED
    return value


def _local_exchange_identifier_exists(store: StateStore, identifier: str) -> bool:
    return any(order.intent.exchange_identifier == identifier for order in store.list_orders())
