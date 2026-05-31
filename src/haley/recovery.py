from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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
    status: RecoveryStepStatus
    steps: list[RecoveryStep]


class RecoveryManager:
    def __init__(self, store: StateStore, exchange: object) -> None:
        self._store = store
        self._exchange = exchange

    def run(self) -> RecoveryRun:
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
                status=RecoveryStepStatus.FAILED,
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

        if mismatch_count:
            self._store.save_reconciliation_state(
                ReconciliationState(
                    status=ReconciliationStatus.MISMATCHED,
                    mismatch_count=mismatch_count,
                )
            )
        steps.append(
            RecoveryStep(
                name="order_detail_reconciliation",
                status=RecoveryStepStatus.SUCCEEDED,
                detail=f"checked={checked}",
            )
        )

        return RecoveryRun(status=RecoveryStepStatus.RUNNING, steps=steps)


def _redact_text(value: str) -> str:
    lowered = value.lower()
    for marker in ("secret", "jwt", "nonce", "query_hash"):
        if marker in lowered:
            return REDACTED
    return value


def _local_exchange_identifier_exists(store: StateStore, identifier: str) -> bool:
    return any(order.intent.exchange_identifier == identifier for order in store.list_orders())
