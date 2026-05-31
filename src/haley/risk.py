from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

from haley.domain import (
    Alert,
    AlertSeverity,
    DataQualityState,
    ModeState,
    ReconciliationState,
    RiskBlock,
    RiskBlockReason,
    RuntimeMode,
)
from haley.state_store import StateStore


@dataclass(frozen=True)
class RiskLimits:
    max_daily_loss_pct: Decimal = Decimal("0.02")
    max_consecutive_stops: int = 3
    max_symbol_exposure_pct: Decimal = Decimal("0.25")
    max_total_crypto_exposure_pct: Decimal = Decimal("0.60")


@dataclass(frozen=True)
class RiskMetrics:
    account_equity: Decimal | None = None
    daily_realized_pnl: Decimal = Decimal("0")
    consecutive_stops: int = 0
    symbol_exposure: dict[str, Decimal] = field(default_factory=dict)
    total_crypto_exposure: Decimal = Decimal("0")
    balance_synced: bool = True
    order_permission_ok: bool = True


@dataclass(frozen=True)
class RiskContext:
    mode: ModeState
    data_quality: DataQualityState | None = None
    reconciliation: ReconciliationState | None = None
    market: str | None = None
    metrics: RiskMetrics = field(default_factory=RiskMetrics)
    limits: RiskLimits = field(default_factory=RiskLimits)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: list[RiskBlockReason] = field(default_factory=list)


class RiskManager:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    def evaluate_new_entry(self, context: RiskContext) -> RiskDecision:
        reasons: list[RiskBlockReason] = []

        if context.mode.kill_switch_enabled or context.mode.mode is RuntimeMode.KILL_SWITCHED:
            reasons.append(RiskBlockReason.KILL_SWITCH_ON)

        if context.mode.mode is RuntimeMode.RECOVERY_ONLY:
            reasons.append(RiskBlockReason.RECOVERY_INCOMPLETE)

        reconciliation = context.reconciliation or self._store.get_reconciliation_state()
        if reconciliation.status.value != "NOT_STARTED" and not reconciliation.allows_new_entry:
            reasons.append(RiskBlockReason.RECOVERY_INCOMPLETE)

        if _daily_loss_limit_exceeded(context.metrics, context.limits):
            reasons.append(RiskBlockReason.DAILY_LOSS_LIMIT)

        if context.metrics.consecutive_stops >= context.limits.max_consecutive_stops:
            reasons.append(RiskBlockReason.CONSECUTIVE_STOP_LIMIT)

        if _exposure_limit_exceeded(context):
            reasons.append(RiskBlockReason.EXPOSURE_LIMIT)

        if not context.metrics.balance_synced:
            reasons.append(RiskBlockReason.BALANCE_SYNC_FAILED)

        if not context.metrics.order_permission_ok:
            reasons.append(RiskBlockReason.ORDER_PERMISSION_ERROR)

        if self._has_unprotected_position():
            reasons.append(RiskBlockReason.UNPROTECTED_POSITION)

        if context.data_quality is not None:
            if context.data_quality.stale:
                reasons.append(RiskBlockReason.DATA_STALE)
            if context.data_quality.rest_ws_mismatch:
                reasons.append(RiskBlockReason.DATA_MISMATCH)
            if context.data_quality.market_warning:
                reasons.append(RiskBlockReason.MARKET_WARNING)

        for reason in reasons:
            self._store.record_risk_block(
                RiskBlock(
                    reason=reason,
                    market=context.market,
                    detail=_detail_for(reason),
                )
            )
            if reason is RiskBlockReason.UNPROTECTED_POSITION:
                self._store.create_alert(
                    Alert(
                        alert_id=f"alert_{uuid4().hex}",
                        severity=AlertSeverity.CRITICAL,
                        message="UNPROTECTED_POSITION: An open position has no stop protection.",
                    )
                )

        return RiskDecision(allowed=not reasons, reasons=reasons)

    def _has_unprotected_position(self) -> bool:
        return any(
            position.volume > 0 and not position.stop_protected
            for position in self._store.list_positions()
        )


def _detail_for(reason: RiskBlockReason) -> str:
    details = {
        RiskBlockReason.KILL_SWITCH_ON: "Kill switch is enabled.",
        RiskBlockReason.RECOVERY_INCOMPLETE: "Recovery or reconciliation is incomplete.",
        RiskBlockReason.DATA_STALE: "Market data is stale.",
        RiskBlockReason.DATA_MISMATCH: "REST and WebSocket data mismatch.",
        RiskBlockReason.MARKET_WARNING: "Market warning or caution is active.",
        RiskBlockReason.UNPROTECTED_POSITION: "An open position has no stop protection.",
        RiskBlockReason.DAILY_LOSS_LIMIT: "Daily realized loss limit exceeded.",
        RiskBlockReason.CONSECUTIVE_STOP_LIMIT: "Consecutive stop limit exceeded.",
        RiskBlockReason.EXPOSURE_LIMIT: "Exposure limit exceeded.",
        RiskBlockReason.BALANCE_SYNC_FAILED: "Balance and locked amount sync failed.",
        RiskBlockReason.ORDER_PERMISSION_ERROR: "Order permission check failed.",
    }
    return details.get(reason, reason.value)


def _daily_loss_limit_exceeded(metrics: RiskMetrics, limits: RiskLimits) -> bool:
    if metrics.account_equity is None or metrics.account_equity <= 0:
        return False
    max_loss = metrics.account_equity * limits.max_daily_loss_pct
    return metrics.daily_realized_pnl <= -max_loss


def _exposure_limit_exceeded(context: RiskContext) -> bool:
    equity = context.metrics.account_equity
    if equity is None or equity <= 0:
        return False

    if context.market is not None:
        symbol_exposure = context.metrics.symbol_exposure.get(context.market, Decimal("0"))
        if symbol_exposure > equity * context.limits.max_symbol_exposure_pct:
            return True

    return (
        context.metrics.total_crypto_exposure
        > equity * context.limits.max_total_crypto_exposure_pct
    )
