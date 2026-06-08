from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class RuntimeMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"
    RECOVERY_ONLY = "RECOVERY_ONLY"
    KILL_SWITCHED = "KILL_SWITCHED"


class OrderSide(StrEnum):
    BID = "bid"
    ASK = "ask"


class OrderType(StrEnum):
    LIMIT = "limit"
    PRICE = "price"
    MARKET = "market"


class OrderStatus(StrEnum):
    PLANNED = "PLANNED"
    SUBMITTING = "SUBMITTING"
    UNKNOWN = "UNKNOWN"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    CANCEL_FAILED = "CANCEL_FAILED"
    REJECTED = "REJECTED"
    RECONCILED = "RECONCILED"


class ExecutionEventType(StrEnum):
    ORDER_INTENT_CREATED = "ORDER_INTENT_CREATED"
    ORDER_TRANSITION = "ORDER_TRANSITION"
    FILL_RECORDED = "FILL_RECORDED"
    RISK_BLOCKED = "RISK_BLOCKED"
    DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    ALERT_CREATED = "ALERT_CREATED"


class RiskBlockReason(StrEnum):
    KILL_SWITCH_ON = "KILL_SWITCH_ON"
    RECOVERY_INCOMPLETE = "RECOVERY_INCOMPLETE"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    DATA_STALE = "DATA_STALE"
    DATA_MISMATCH = "DATA_MISMATCH"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    CONSECUTIVE_STOP_LIMIT = "CONSECUTIVE_STOP_LIMIT"
    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    UNPROTECTED_POSITION = "UNPROTECTED_POSITION"
    BALANCE_SYNC_FAILED = "BALANCE_SYNC_FAILED"
    ORDER_PERMISSION_ERROR = "ORDER_PERMISSION_ERROR"
    MARKET_WARNING = "MARKET_WARNING"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ReconciliationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    FAILED = "FAILED"


ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PLANNED: frozenset({OrderStatus.SUBMITTING, OrderStatus.REJECTED}),
    OrderStatus.SUBMITTING: frozenset(
        {OrderStatus.UNKNOWN, OrderStatus.ACCEPTED, OrderStatus.REJECTED}
    ),
    OrderStatus.UNKNOWN: frozenset(
        {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.RECONCILED}
    ),
    OrderStatus.ACCEPTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_REQUESTED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.FILLED, OrderStatus.CANCEL_REQUESTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.CANCEL_REQUESTED: frozenset(
        {OrderStatus.CANCELLED, OrderStatus.CANCEL_FAILED, OrderStatus.RECONCILED}
    ),
    OrderStatus.CANCEL_FAILED: frozenset(
        {OrderStatus.CANCEL_REQUESTED, OrderStatus.RECONCILED}
    ),
    OrderStatus.FILLED: frozenset({OrderStatus.RECONCILED}),
    OrderStatus.CANCELLED: frozenset({OrderStatus.RECONCILED}),
    OrderStatus.REJECTED: frozenset({OrderStatus.RECONCILED}),
    OrderStatus.RECONCILED: frozenset(),
}

BLOCKS_NEW_ENTRY_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTING,
        OrderStatus.UNKNOWN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_FAILED,
    }
)


def is_order_transition_allowed(
    current_status: OrderStatus, next_status: OrderStatus
) -> bool:
    return next_status in ALLOWED_ORDER_TRANSITIONS[current_status]


def blocks_new_entry_statuses() -> set[OrderStatus]:
    return set(BLOCKS_NEW_ENTRY_STATUSES)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _require_decimal(name: str, value: Decimal | None) -> None:
    if value is not None and not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal, got {type(value).__name__}")


@dataclass(frozen=True)
class ModeState:
    mode: RuntimeMode = RuntimeMode.PAPER
    live_trading_enabled: bool = False
    paper_allow_real_order_api: bool = False
    kill_switch_enabled: bool = False
    updated_at: datetime = field(default_factory=_utc_now)

    @property
    def allows_real_order_api(self) -> bool:
        return self.mode is RuntimeMode.LIVE and self.live_trading_enabled


@dataclass(frozen=True)
class OrderIntent:
    client_order_key: str
    market: str
    side: OrderSide
    order_type: OrderType
    quote_amount: Decimal | None
    volume: Decimal | None
    limit_price: Decimal | None
    created_at: datetime
    request_hash: str | None = None
    exchange_identifier: str | None = None

    def __post_init__(self) -> None:
        _require_decimal("quote_amount", self.quote_amount)
        _require_decimal("volume", self.volume)
        _require_decimal("limit_price", self.limit_price)
        if not self.client_order_key:
            raise ValueError("client_order_key is required")
        if not self.market.startswith("KRW-"):
            raise ValueError("only KRW spot markets are supported")


@dataclass(frozen=True)
class OrderState:
    order_id: str
    intent: OrderIntent
    status: OrderStatus
    version: int = 1
    updated_at: datetime = field(default_factory=_utc_now)

    def transition_to(self, next_status: OrderStatus) -> OrderState:
        if not is_order_transition_allowed(self.status, next_status):
            raise ValueError(f"invalid order transition: {self.status} -> {next_status}")
        return OrderState(
            order_id=self.order_id,
            intent=self.intent,
            status=next_status,
            version=self.version + 1,
        )

    @property
    def blocks_new_entry(self) -> bool:
        return self.status in BLOCKS_NEW_ENTRY_STATUSES


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    market: str
    side: OrderSide
    price: Decimal
    volume: Decimal
    fee: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        _require_decimal("price", self.price)
        _require_decimal("volume", self.volume)
        _require_decimal("fee", self.fee)


@dataclass(frozen=True)
class PositionState:
    market: str
    volume: Decimal
    average_entry_price: Decimal
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    stop_protected: bool = False
    stop_price: Decimal | None = None
    target1_price: Decimal | None = None
    target2_price: Decimal | None = None
    trailing_stop_price: Decimal | None = None
    management_stage: str = "OPEN"
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        _require_decimal("volume", self.volume)
        _require_decimal("average_entry_price", self.average_entry_price)
        _require_decimal("realized_pnl", self.realized_pnl)
        _require_decimal("unrealized_pnl", self.unrealized_pnl)
        _require_decimal("stop_price", self.stop_price)
        _require_decimal("target1_price", self.target1_price)
        _require_decimal("target2_price", self.target2_price)
        _require_decimal("trailing_stop_price", self.trailing_stop_price)


@dataclass(frozen=True)
class StopProtectionState:
    market: str
    position_volume: Decimal
    protected: bool = False
    stop_price: Decimal | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        _require_decimal("position_volume", self.position_volume)
        _require_decimal("stop_price", self.stop_price)


@dataclass(frozen=True)
class ExecutionEvent:
    event_id: str
    order_id: str | None
    event_type: ExecutionEventType
    occurred_at: datetime
    payload: Mapping[str, Any]
    request_id: str | None = None
    idempotency_key: str | None = None
    operator_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class RiskBlock:
    reason: RiskBlockReason
    market: str | None
    detail: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class DataQualityState:
    stale: bool
    rest_ws_mismatch: bool
    market_warning: bool = False
    orderbook_gap: bool = False
    last_ws_received_at: datetime | None = None
    last_rest_sync_at: datetime | None = None
    last_ticker_received_at: datetime | None = None
    last_trade_received_at: datetime | None = None
    last_orderbook_received_at: datetime | None = None
    last_candle_received_at: datetime | None = None

    @property
    def allows_new_entry(self) -> bool:
        return not (
            self.stale
            or self.rest_ws_mismatch
            or self.market_warning
            or self.orderbook_gap
        )


@dataclass(frozen=True)
class ReconciliationState:
    status: ReconciliationStatus = ReconciliationStatus.NOT_STARTED
    mismatch_count: int = 0
    last_checked_at: datetime | None = None
    operator_resume_required: bool = False

    @property
    def allows_new_entry(self) -> bool:
        return (
            self.status is ReconciliationStatus.MATCHED
            and self.mismatch_count == 0
            and not self.operator_resume_required
        )


@dataclass(frozen=True)
class Alert:
    alert_id: str
    severity: AlertSeverity
    message: str
    created_at: datetime = field(default_factory=_utc_now)
    acknowledged_at: datetime | None = None
