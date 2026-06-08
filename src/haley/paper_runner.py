from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4

from haley.api_contracts import StateChangeRequest
from haley.domain import ModeState, OrderSide, OrderStatus, OrderType, RuntimeMode
from haley.experiments import SignalJournalEntry
from haley.market_data import (
    CandleStore,
    CandleUsePolicy,
    parse_upbit_rest_minute_candle,
    select_top_krw_alt_markets,
)
from haley.orders import DuplicateMarketOrderError, OrderCoordinator
from haley.paper import PaperExecutionEngine, PaperPortfolio
from haley.risk import RiskContext, RiskManager, RiskMetrics
from haley.state_store import StateStore
from haley.strategy import StrategySignal, TradePlan, UfsR1SignalEngine


@dataclass(frozen=True)
class PaperRunnerState:
    running: bool = False
    mode: str = RuntimeMode.PAPER.value
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_tick_at: datetime | None = None
    selected_markets: list[str] = field(default_factory=list)
    last_action: str | None = None
    last_block_reason: str | None = None
    last_signal: dict[str, Any] | None = None
    last_trade_plan: dict[str, Any] | None = None
    paper_cash_krw: str = "0"
    paper_locked_cash_krw: str = "0"


class PaperRunner:
    def __init__(
        self,
        store: StateStore,
        initial_cash_krw: Decimal = Decimal("1000000"),
        ticker_client: Any | None = None,
        top_alt_count: int = 10,
        include_major_markets: bool = False,
        mode: ModeState | None = None,
        selected_markets: list[str] | None = None,
        price_by_market: dict[str, Decimal] | None = None,
        candle_store: CandleStore | None = None,
        signal_engine: UfsR1SignalEngine | None = None,
        order_quote_amount_krw: Decimal = Decimal("50000"),
        fee_rate: Decimal = Decimal("0.0005"),
        tick_interval_sec: float = 5.0,
        session_id: str = "paper_session_default",
        candle_grace_ms: int = 0,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._initial_cash_krw = initial_cash_krw
        self._ticker_client = ticker_client
        self._top_alt_count = top_alt_count
        self._include_major_markets = include_major_markets
        self._mode = mode or ModeState()
        self._risk_manager = RiskManager(store)
        self._order_coordinator = OrderCoordinator(store)
        self._price_by_market = dict(price_by_market or {})
        self._candle_store = candle_store or CandleStore()
        self._signal_engine = signal_engine or UfsR1SignalEngine()
        self._order_quote_amount_krw = order_quote_amount_krw
        self._fee_rate = fee_rate
        self._tick_interval_sec = tick_interval_sec
        self._session_id = session_id
        self._candle_grace_ms = candle_grace_ms
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._state = PaperRunnerState(
            selected_markets=list(selected_markets or []),
            paper_cash_krw=str(self._portfolio().cash_krw),
            paper_locked_cash_krw=str(self._portfolio().locked_cash_krw),
        )

    def start(self) -> PaperRunnerState:
        with self._lock:
            if self._state.running:
                return self._state
            self._stop_event.clear()
            self._state = self._with_portfolio_unlocked(
                running=True,
                started_at=datetime.now(UTC),
                stopped_at=None,
                last_action="STARTED",
            )
        self.tick()
        self._thread = Thread(target=self._run_loop, name="haley-paper-runner", daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> PaperRunnerState:
        thread = self._thread
        self._stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(self._tick_interval_sec * 2, 1.0))
        with self._lock:
            if not self._state.running:
                return self._state
            self._state = self._with_portfolio_unlocked(
                running=False,
                stopped_at=datetime.now(UTC),
                last_action="STOPPED",
            )
            return self._state

    def status(self) -> PaperRunnerState:
        with self._lock:
            self._state = self._with_portfolio_unlocked()
            return self._state

    def refresh_markets(self) -> PaperRunnerState:
        if self._ticker_client is None:
            return self.status()
        tickers = self._ticker_client.list_all_tickers(["KRW"])
        markets = select_top_krw_alt_markets(
            tickers,
            count=self._top_alt_count,
            include_major_markets=self._include_major_markets,
        )
        for ticker in tickers:
            market = str(ticker.get("market", ""))
            if market in markets and ticker.get("trade_price") is not None:
                self._price_by_market[market] = Decimal(str(ticker["trade_price"]))
        with self._lock:
            self._state = self._with_portfolio_unlocked(
                selected_markets=markets,
                last_action="MARKETS_REFRESHED",
            )
            return self._state

    def set_market_price(self, market: str, price: Decimal) -> None:
        self._price_by_market[market] = price

    def tick(self) -> PaperRunnerState:
        if not self._state.selected_markets and self._ticker_client is not None:
            self.refresh_markets()
        mode = self._store.get_mode_state()
        self._mode = mode
        market = self._state.selected_markets[0] if self._state.selected_markets else None
        price = None if market is None else self._price_by_market.get(market)
        if market is not None and price is not None:
            managed = self._manage_open_position(market=market, price=price)
            if managed is not None:
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="PAPER_POSITION_MANAGED",
                        last_block_reason=None,
                    )
                    return self._state
        quality = None if market is None else self._store.list_data_quality_states().get(market)
        decision = self._risk_manager.evaluate_new_entry(
            RiskContext(
                mode=mode,
                data_quality=quality,
                market=market,
                metrics=self._risk_metrics(),
            )
        )
        if decision.allowed and market is not None:
            if price is None:
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="NO_PRICE",
                        last_block_reason="NO_PRICE",
                    )
                    return self._state
            if _has_open_position(self._store, market):
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="POSITION_OPEN",
                        last_block_reason="POSITION_OPEN",
                    )
                    return self._state
            self._refresh_public_candles(market, unit=5)
            self._refresh_public_candles(market, unit=15)
            if self._is_waiting_for_candle_grace(market):
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="WAITING_FOR_CANDLE_GRACE",
                        last_block_reason="WAITING_FOR_CANDLE_GRACE",
                        last_signal=None,
                        last_trade_plan=None,
                    )
                    return self._state
            signal = self._signal_engine.evaluate(
                market=market,
                candles_5m=self._candle_store.list(market, "5m"),
                candles_15m=self._candle_store.list(market, "15m"),
            )
            if signal is None:
                self._record_signal_journal(
                    market=market,
                    signal=None,
                    trade_plan=None,
                    rejected_reasons=["NO_SIGNAL"],
                )
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="NO_SIGNAL",
                        last_block_reason="NO_SIGNAL",
                        last_signal=None,
                        last_trade_plan=None,
                    )
                    return self._state
            trade_plan = _trade_plan_at_price(
                signal=signal,
                quote_amount=self._order_quote_amount_krw,
                entry_price=price,
            )
            self._record_signal_journal(
                market=market,
                signal=signal,
                trade_plan=trade_plan,
                rejected_reasons=[],
            )
            try:
                self._fill_paper_entry(trade_plan=trade_plan)
            except DuplicateMarketOrderError:
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="BLOCKED",
                        last_block_reason="UNSETTLED_ORDER",
                        last_signal=_decimal_dict(signal),
                        last_trade_plan=_decimal_dict(trade_plan),
                    )
                    return self._state
            with self._lock:
                self._state = self._with_portfolio_unlocked(
                    last_tick_at=datetime.now(UTC),
                    last_action="PAPER_FILLED",
                    last_block_reason=None,
                    last_signal=_decimal_dict(signal),
                    last_trade_plan=_decimal_dict(trade_plan),
                )
                return self._state
        with self._lock:
            self._state = self._with_portfolio_unlocked(
                last_tick_at=datetime.now(UTC),
                last_action="BLOCKED" if not decision.allowed else "RISK_PASSED",
                last_block_reason=None if decision.allowed else decision.reasons[0].value,
            )
            return self._state

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(self._tick_interval_sec)
        with self._lock:
            self._state = self._with_portfolio_unlocked(
                running=False,
                stopped_at=datetime.now(UTC),
                last_action="STOPPED",
            )

    def _fill_paper_entry(self, trade_plan: TradePlan) -> None:
        state_change = StateChangeRequest(
            request_id="req_paper_runner",
            idempotency_key=f"idem_paper_runner_{trade_plan.market}",
            operator_id="paper-runner",
            reason=f"{trade_plan.strategy} paper runner virtual fill",
        )
        order = self._order_coordinator.create_entry_order(
            market=trade_plan.market,
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            quote_amount=trade_plan.quote_amount,
            volume=trade_plan.volume,
            limit_price=trade_plan.entry_price,
            exchange_identifier=None,
            state_change=state_change,
        )
        self._store.transition_order(
            order.order_id,
            OrderStatus.SUBMITTING,
            state_change.request_id,
            f"{state_change.idempotency_key}_submit",
            state_change.operator_id,
            state_change.reason,
        )
        self._store.transition_order(
            order.order_id,
            OrderStatus.ACCEPTED,
            state_change.request_id,
            f"{state_change.idempotency_key}_accepted",
            state_change.operator_id,
            state_change.reason,
        )
        portfolio = self._portfolio()
        engine = PaperExecutionEngine(
            store=self._store,
            portfolio=portfolio,
            fee_rate=self._fee_rate,
            allow_real_order_api=False,
        )
        engine.reserve_buy_order(order.order_id)
        engine.fill_buy_order(
            order_id=order.order_id,
            price=trade_plan.entry_price,
            volume=trade_plan.volume,
            state_change=state_change,
            stop_price=trade_plan.stop_price,
            target1_price=trade_plan.target1_price,
            target2_price=trade_plan.target2_price,
        )
        self._store.save_paper_portfolio(portfolio)

    def _is_waiting_for_candle_grace(self, market: str) -> bool:
        if self._candle_grace_ms <= 0:
            return False
        candles = self._candle_store.list(market, "5m")
        if not candles:
            return False
        decision = CandleUsePolicy(candle_grace_ms=self._candle_grace_ms).evaluate(
            closed_at=candles[-1].candle_time,
            now=self._now_provider(),
        )
        return not decision.usable

    def _manage_open_position(self, market: str, price: Decimal) -> str | None:
        portfolio = self._portfolio()
        engine = PaperExecutionEngine(
            store=self._store,
            portfolio=portfolio,
            fee_rate=self._fee_rate,
            allow_real_order_api=False,
        )
        action = engine.manage_position(market=market, price=price)
        if action is not None:
            self._store.save_paper_portfolio(portfolio)
        return action

    def _refresh_public_candles(self, market: str, unit: int) -> None:
        if self._candle_store.list(market, f"{unit}m"):
            return
        if self._ticker_client is None:
            return
        list_minute_candles = getattr(self._ticker_client, "list_minute_candles", None)
        if list_minute_candles is None:
            return
        for payload in list_minute_candles(market=market, unit=unit, count=100):
            self._candle_store.upsert(
                parse_upbit_rest_minute_candle(
                    market=market,
                    unit=unit,
                    payload=payload,
                )
            )

    def _risk_metrics(self) -> RiskMetrics:
        portfolio = self._portfolio()
        positions = self._store.list_positions()
        equity = portfolio.cash_krw + portfolio.locked_cash_krw
        symbol_exposure: dict[str, Decimal] = {}
        total_exposure = Decimal("0")
        daily_realized_pnl = Decimal("0")
        for position in positions:
            price = self._price_by_market.get(
                position.market,
                position.average_entry_price,
            )
            exposure = position.volume * price
            symbol_exposure[position.market] = exposure
            total_exposure += exposure
            equity += exposure
            daily_realized_pnl += position.realized_pnl
        return RiskMetrics(
            account_equity=equity,
            daily_realized_pnl=daily_realized_pnl,
            symbol_exposure=symbol_exposure,
            total_crypto_exposure=total_exposure,
            balance_synced=True,
            order_permission_ok=True,
        )

    def _record_signal_journal(
        self,
        *,
        market: str,
        signal: StrategySignal | None,
        trade_plan: TradePlan | None,
        rejected_reasons: list[str],
    ) -> None:
        self._store.save_signal_journal_entry(
            SignalJournalEntry(
                entry_id=f"journal_{uuid4().hex}",
                session_id=self._session_id,
                market=market,
                strategy="UFS-R1" if signal is None else signal.strategy,
                signal_score=0 if signal is None else signal.signal_score,
                reasons=[] if signal is None else list(signal.reasons),
                rejected_reasons=list(rejected_reasons),
                entry_price=None if trade_plan is None else trade_plan.entry_price,
                stop_price=None if trade_plan is None else trade_plan.stop_price,
                target1_price=None if trade_plan is None else trade_plan.target1_price,
                target2_price=None if trade_plan is None else trade_plan.target2_price,
            )
        )

    def _with_portfolio_unlocked(self, **changes: object) -> PaperRunnerState:
        portfolio = self._portfolio()
        values = {
            "running": self._state.running,
            "mode": self._mode.mode.value,
            "started_at": self._state.started_at,
            "stopped_at": self._state.stopped_at,
            "last_tick_at": self._state.last_tick_at,
            "selected_markets": list(self._state.selected_markets),
            "last_action": self._state.last_action,
            "last_block_reason": self._state.last_block_reason,
            "last_signal": self._state.last_signal,
            "last_trade_plan": self._state.last_trade_plan,
            "paper_cash_krw": str(portfolio.cash_krw),
            "paper_locked_cash_krw": str(portfolio.locked_cash_krw),
        }
        values.update(changes)
        return PaperRunnerState(**values)

    def _portfolio(self) -> PaperPortfolio:
        try:
            return self._store.get_paper_portfolio()
        except KeyError:
            portfolio = PaperPortfolio(initial_cash_krw=self._initial_cash_krw)
            self._store.save_paper_portfolio(portfolio)
            return portfolio


def _trade_plan_at_price(
    signal: StrategySignal,
    quote_amount: Decimal,
    entry_price: Decimal,
) -> TradePlan:
    risk = signal.entry_price - signal.stop_price
    stop_price = entry_price - risk
    return TradePlan(
        strategy=signal.strategy,
        market=signal.market,
        side="bid",
        order_type="limit",
        quote_amount=quote_amount,
        entry_price=entry_price,
        volume=quote_amount / entry_price,
        stop_price=stop_price,
        target1_price=entry_price + risk,
        target2_price=entry_price + risk * Decimal("2"),
        signal_score=signal.signal_score,
        reasons=list(signal.reasons),
        invalidation_conditions=list(signal.invalidation_conditions),
    )


def _decimal_dict(item: object) -> dict[str, Any]:
    values = asdict(item)
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


def _has_open_position(store: StateStore, market: str) -> bool:
    return any(
        position.market == market and position.volume > 0
        for position in store.list_positions()
    )
