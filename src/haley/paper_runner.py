from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, Lock, Thread
from typing import Any

from haley.api_contracts import StateChangeRequest
from haley.domain import ModeState, OrderSide, OrderStatus, OrderType, RuntimeMode
from haley.market_data import select_top_krw_alt_markets
from haley.orders import OrderCoordinator
from haley.paper import PaperExecutionEngine, PaperPortfolio
from haley.risk import RiskContext, RiskManager
from haley.state_store import StateStore


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
        order_quote_amount_krw: Decimal = Decimal("50000"),
        fee_rate: Decimal = Decimal("0.0005"),
        tick_interval_sec: float = 5.0,
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
        self._order_quote_amount_krw = order_quote_amount_krw
        self._fee_rate = fee_rate
        self._tick_interval_sec = tick_interval_sec
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

    def tick(self) -> PaperRunnerState:
        if not self._state.selected_markets and self._ticker_client is not None:
            self.refresh_markets()
        market = self._state.selected_markets[0] if self._state.selected_markets else None
        quality = None if market is None else self._store.list_data_quality_states().get(market)
        decision = self._risk_manager.evaluate_new_entry(
            RiskContext(
                mode=self._mode,
                data_quality=quality,
                market=market,
            )
        )
        if decision.allowed and market is not None:
            price = self._price_by_market.get(market)
            if price is None:
                with self._lock:
                    self._state = self._with_portfolio_unlocked(
                        last_tick_at=datetime.now(UTC),
                        last_action="NO_PRICE",
                        last_block_reason="NO_PRICE",
                    )
                    return self._state
            self._fill_paper_entry(market=market, price=price)
            with self._lock:
                self._state = self._with_portfolio_unlocked(
                    last_tick_at=datetime.now(UTC),
                    last_action="PAPER_FILLED",
                    last_block_reason=None,
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

    def _fill_paper_entry(self, market: str, price: Decimal) -> None:
        state_change = StateChangeRequest(
            request_id="req_paper_runner",
            idempotency_key=f"idem_paper_runner_{market}",
            operator_id="paper-runner",
            reason="paper runner virtual fill",
        )
        volume = self._order_quote_amount_krw / price
        order = self._order_coordinator.create_entry_order(
            market=market,
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            quote_amount=self._order_quote_amount_krw,
            volume=volume,
            limit_price=price,
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
            price=price,
            volume=volume,
            state_change=state_change,
        )
        self._store.save_paper_portfolio(portfolio)

    def _with_portfolio_unlocked(self, **changes: object) -> PaperRunnerState:
        portfolio = self._portfolio()
        values = {
            "running": self._state.running,
            "mode": self._state.mode,
            "started_at": self._state.started_at,
            "stopped_at": self._state.stopped_at,
            "last_tick_at": self._state.last_tick_at,
            "selected_markets": list(self._state.selected_markets),
            "last_action": self._state.last_action,
            "last_block_reason": self._state.last_block_reason,
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
