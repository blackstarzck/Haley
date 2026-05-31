from __future__ import annotations

from dataclasses import dataclass

from haley.domain import ReconciliationStatus
from haley.recovery import RecoveryManager, RecoveryStepStatus
from haley.state_store import StateStore


@dataclass
class FakeExchange:
    accounts: list[dict[str, str]]
    open_orders: list[dict[str, str]] | None = None
    order_details: dict[str, dict[str, str]] | None = None

    def list_accounts(self) -> list[dict[str, str]]:
        return self.accounts

    def list_open_orders(self) -> list[dict[str, str]]:
        return self.open_orders or []

    def get_order_detail(self, identifier: str) -> dict[str, str]:
        return (self.order_details or {})[identifier]


def test_recovery_manager_records_balance_lookup_and_reconciliation_running() -> None:
    store = StateStore.in_memory()
    manager = RecoveryManager(
        store=store,
        exchange=FakeExchange(accounts=[{"currency": "KRW", "balance": "1000000"}]),
    )

    run = manager.run()

    assert run.status is RecoveryStepStatus.RUNNING
    assert run.steps[0].name == "balance_lookup"
    assert run.steps[0].status is RecoveryStepStatus.SUCCEEDED
    assert run.steps[0].detail == "accounts=1"
    assert store.get_reconciliation_state().status is ReconciliationStatus.RUNNING


def test_recovery_manager_records_failure_without_secret_details() -> None:
    class FailingExchange:
        def list_accounts(self) -> list[dict[str, str]]:
            raise RuntimeError("secret_key=hidden failed")

    store = StateStore.in_memory()
    manager = RecoveryManager(store=store, exchange=FailingExchange())

    run = manager.run()

    assert run.status is RecoveryStepStatus.FAILED
    assert "secret" not in run.steps[0].detail.lower()
    assert store.get_reconciliation_state().status is ReconciliationStatus.FAILED


def test_recovery_manager_checks_open_orders_and_records_mismatch() -> None:
    store = StateStore.in_memory()
    manager = RecoveryManager(
        store=store,
        exchange=FakeExchange(
            accounts=[{"currency": "KRW", "balance": "1000000"}],
            open_orders=[{"identifier": "upbit-id-1", "market": "KRW-XRP"}],
            order_details={"upbit-id-1": {"identifier": "upbit-id-1", "state": "wait"}},
        ),
    )

    run = manager.run()

    assert [step.name for step in run.steps] == [
        "balance_lookup",
        "open_orders_lookup",
        "order_detail_reconciliation",
    ]
    assert run.steps[1].detail == "open_orders=1"
    assert run.steps[2].detail == "checked=1"
    assert store.get_reconciliation_state().mismatch_count == 1
