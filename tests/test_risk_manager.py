from decimal import Decimal

from haley.domain import (
    DataQualityState,
    ModeState,
    PositionState,
    ReconciliationState,
    ReconciliationStatus,
    RiskBlockReason,
    RuntimeMode,
)
from haley.risk import RiskContext, RiskManager
from haley.risk import RiskLimits, RiskMetrics
from haley.state_store import StateStore


def test_risk_manager_blocks_when_kill_switch_is_enabled() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(mode=ModeState(kill_switch_enabled=True))
    )

    assert not decision.allowed
    assert decision.reasons == [RiskBlockReason.KILL_SWITCH_ON]


def test_risk_manager_blocks_recovery_only_mode() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(mode=ModeState(mode=RuntimeMode.RECOVERY_ONLY))
    )

    assert not decision.allowed
    assert RiskBlockReason.RECOVERY_INCOMPLETE in decision.reasons


def test_risk_manager_blocks_unhealthy_data_quality() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            data_quality=DataQualityState(stale=True, rest_ws_mismatch=False),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.DATA_STALE in decision.reasons


def test_risk_manager_blocks_reconciliation_mismatch() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            reconciliation=ReconciliationState(
                status=ReconciliationStatus.MISMATCHED,
                mismatch_count=1,
            ),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.RECOVERY_INCOMPLETE in decision.reasons


def test_risk_manager_blocks_unprotected_positions() -> None:
    store = StateStore.in_memory()
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
            stop_protected=False,
        )
    )
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(RiskContext(mode=ModeState()))

    assert not decision.allowed
    assert RiskBlockReason.UNPROTECTED_POSITION in decision.reasons
    assert store.list_risk_blocks()[0].reason is RiskBlockReason.UNPROTECTED_POSITION


def test_risk_manager_allows_when_no_blocks_exist() -> None:
    store = StateStore.in_memory()
    store.save_reconciliation_state(
        ReconciliationState(status=ReconciliationStatus.MATCHED)
    )
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            data_quality=DataQualityState(stale=False, rest_ws_mismatch=False),
        )
    )

    assert decision.allowed
    assert decision.reasons == []


def test_risk_manager_blocks_daily_loss_limit() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            metrics=RiskMetrics(
                account_equity=Decimal("1000000"),
                daily_realized_pnl=Decimal("-25000"),
            ),
            limits=RiskLimits(max_daily_loss_pct=Decimal("0.02")),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.DAILY_LOSS_LIMIT in decision.reasons


def test_risk_manager_blocks_consecutive_stop_limit() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            metrics=RiskMetrics(consecutive_stops=3),
            limits=RiskLimits(max_consecutive_stops=3),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.CONSECUTIVE_STOP_LIMIT in decision.reasons


def test_risk_manager_blocks_symbol_exposure_limit() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            market="KRW-XRP",
            metrics=RiskMetrics(
                account_equity=Decimal("1000000"),
                symbol_exposure={"KRW-XRP": Decimal("260000")},
            ),
            limits=RiskLimits(max_symbol_exposure_pct=Decimal("0.25")),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.EXPOSURE_LIMIT in decision.reasons


def test_risk_manager_blocks_total_crypto_exposure_limit() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            metrics=RiskMetrics(
                account_equity=Decimal("1000000"),
                total_crypto_exposure=Decimal("610000"),
            ),
            limits=RiskLimits(max_total_crypto_exposure_pct=Decimal("0.60")),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.EXPOSURE_LIMIT in decision.reasons


def test_risk_manager_blocks_balance_sync_failure_and_permission_error() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(),
            metrics=RiskMetrics(
                balance_synced=False,
                order_permission_ok=False,
            ),
        )
    )

    assert not decision.allowed
    assert RiskBlockReason.BALANCE_SYNC_FAILED in decision.reasons
    assert RiskBlockReason.ORDER_PERMISSION_ERROR in decision.reasons


def test_risk_manager_creates_alert_for_unprotected_position() -> None:
    store = StateStore.in_memory()
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
            stop_protected=False,
        )
    )
    manager = RiskManager(store)

    manager.evaluate_new_entry(RiskContext(mode=ModeState(), market="KRW-XRP"))

    alerts = store.list_alerts()
    assert len(alerts) == 1
    assert alerts[0].severity.value == "CRITICAL"
    assert "UNPROTECTED_POSITION" in alerts[0].message


def test_risk_manager_reports_blocks_in_execution_priority_order() -> None:
    store = StateStore.in_memory()
    manager = RiskManager(store)

    decision = manager.evaluate_new_entry(
        RiskContext(
            mode=ModeState(kill_switch_enabled=True),
            data_quality=DataQualityState(stale=True, rest_ws_mismatch=False),
            metrics=RiskMetrics(
                account_equity=Decimal("1000000"),
                total_crypto_exposure=Decimal("610000"),
            ),
            limits=RiskLimits(max_total_crypto_exposure_pct=Decimal("0.60")),
        )
    )

    assert decision.reasons == [
        RiskBlockReason.KILL_SWITCH_ON,
        RiskBlockReason.EXPOSURE_LIMIT,
        RiskBlockReason.DATA_STALE,
    ]
