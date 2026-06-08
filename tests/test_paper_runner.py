from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic, sleep

import pytest

from haley.api_contracts import StateChangeRequest
from haley.orders import OrderCoordinator
from haley.market_data import Candle, CandleStore
from haley.paper import PaperPortfolio
from haley.paper_runner import PaperRunner
from haley.domain import (
    DataQualityState,
    ModeState,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionState,
    ReconciliationState,
    ReconciliationStatus,
    RuntimeMode,
)
from haley.state_store import StateStore


class FakeTickerClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def list_all_tickers(self, quote_currencies: list[str]) -> list[dict[str, object]]:
        self.calls.append(quote_currencies)
        return [
            {"market": "KRW-BTC", "acc_trade_price_24h": "900", "trade_price": "1000"},
            {"market": "KRW-XRP", "acc_trade_price_24h": "700", "trade_price": "500"},
            {"market": "KRW-DOGE", "acc_trade_price_24h": "800", "trade_price": "100"},
        ]


class RealOrderApiTrap(FakeTickerClient):
    def create_order(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Runner must not call real order creation API")

    def cancel_order(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Runner must not call real order cancel API")


class PublicCandleTickerClient(FakeTickerClient):
    def __init__(self) -> None:
        super().__init__()
        self.candle_calls: list[tuple[str, int, int]] = []

    def list_minute_candles(
        self,
        market: str,
        unit: int,
        count: int,
    ) -> list[dict[str, object]]:
        self.candle_calls.append((market, unit, count))
        candles = (
            ufs_r1_signal_candles(market)
            if unit == 5
            else uptrend_15m_candles(market)
        )
        return [
            {
                "candle_date_time_utc": item.candle_time.replace(tzinfo=None).isoformat(),
                "opening_price": str(item.open),
                "high_price": str(item.high),
                "low_price": str(item.low),
                "trade_price": str(item.close),
                "candle_acc_trade_volume": str(item.volume),
            }
            for item in candles
        ]


def test_paper_runner_start_stop_and_status_without_orders() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    runner = PaperRunner(store=store)

    started = runner.start()
    duplicate = runner.start()
    stopped = runner.stop()

    assert started.running is True
    assert duplicate.running is True
    assert duplicate.started_at == started.started_at
    assert stopped.running is False
    assert stopped.stopped_at is not None
    assert store.list_orders() == []


def test_paper_runner_status_includes_virtual_cash() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(
        PaperPortfolio(
            initial_cash_krw=Decimal("1000000"),
            cash_krw=Decimal("900000"),
            locked_cash_krw=Decimal("50000"),
        )
    )
    runner = PaperRunner(store=store)

    state = runner.status()

    assert state.mode == "PAPER"
    assert state.paper_cash_krw == "900000"
    assert state.paper_locked_cash_krw == "50000"
    assert state.selected_markets == []


def test_paper_runner_selects_markets_from_public_tickers() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    ticker_client = FakeTickerClient()
    runner = PaperRunner(
        store=store,
        ticker_client=ticker_client,
        top_alt_count=1,
        include_major_markets=False,
    )

    state = runner.refresh_markets()

    assert ticker_client.calls == [["KRW"]]
    assert state.selected_markets == ["KRW-DOGE"]
    assert store.list_orders() == []


def test_paper_runner_tick_records_risk_block_before_order_creation() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=True, rest_ws_mismatch=False),
    )
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
    )

    state = runner.tick()

    assert state.last_block_reason == "DATA_STALE"
    assert store.list_orders() == []
    assert store.list_risk_blocks()[0].reason.value == "DATA_STALE"


def test_paper_runner_tick_does_not_order_without_ufs_r1_signal() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        order_quote_amount_krw=Decimal("50000"),
    )

    state = runner.tick()

    assert state.last_action == "NO_SIGNAL"
    assert state.last_block_reason == "NO_SIGNAL"
    assert store.list_orders() == []


def test_paper_runner_records_rejected_signal_journal_entry() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        order_quote_amount_krw=Decimal("50000"),
        session_id="session-1",
    )

    runner.tick()

    entries = store.list_signal_journal_entries("session-1")
    assert entries[0].market == "KRW-XRP"
    assert entries[0].rejected_reasons == ["NO_SIGNAL"]
    assert entries[0].signal_score == 0


def test_paper_runner_tick_creates_paper_order_from_ufs_r1_trade_plan() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
        order_quote_amount_krw=Decimal("50000"),
        fee_rate=Decimal("0.0005"),
    )

    state = runner.tick()

    order = store.list_orders()[0]
    portfolio = store.get_paper_portfolio()

    assert state.last_action == "PAPER_FILLED"
    assert state.last_signal is not None
    assert state.last_signal["strategy"] == "UFS-R1"
    assert state.last_trade_plan is not None
    assert state.last_block_reason is None
    assert order.status is OrderStatus.FILLED
    assert len(store.list_fills(order.order_id)) == 1
    position = store.list_positions()[0]
    assert position.market == "KRW-XRP"
    assert position.stop_protected is True
    assert position.stop_price is not None
    assert position.target1_price is not None
    assert store.list_stop_protections("KRW-XRP")[0].protected is True
    assert portfolio.cash_krw == Decimal("949975.0000")


def test_paper_runner_waits_for_candle_grace_before_signal_evaluation() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    candles = ufs_r1_signal_candles("KRW-XRP")
    for item in candles:
        candle_store.upsert(item)
    latest_closed_at = candles[-1].candle_time
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
        candle_grace_ms=500,
        now_provider=lambda: latest_closed_at + timedelta(milliseconds=499),
    )

    state = runner.tick()

    assert state.last_action == "WAITING_FOR_CANDLE_GRACE"
    assert state.last_block_reason == "WAITING_FOR_CANDLE_GRACE"
    assert store.list_orders() == []
    assert store.list_signal_journal_entries("paper_session_default") == []


def test_paper_runner_records_accepted_signal_journal_entry() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
        order_quote_amount_krw=Decimal("50000"),
        fee_rate=Decimal("0.0005"),
        session_id="session-1",
    )

    runner.tick()

    entries = store.list_signal_journal_entries("session-1")
    assert entries[0].market == "KRW-XRP"
    assert entries[0].strategy == "UFS-R1"
    assert entries[0].signal_score > 0
    assert entries[0].rejected_reasons == []
    assert entries[0].entry_price == Decimal("500")


def test_paper_runner_hard_block_overrides_signal_score() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=True, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    )

    state = runner.tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "DATA_STALE"
    assert store.list_orders() == []


@pytest.mark.parametrize(
    "blocking_status",
    [
        OrderStatus.SUBMITTING,
        OrderStatus.UNKNOWN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_FAILED,
    ],
)
def test_paper_runner_does_not_order_when_blocking_order_exists_for_market(
    blocking_status: OrderStatus,
) -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    _create_order_in_status(store, market="KRW-XRP", status=blocking_status)
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    )

    state = runner.tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "UNSETTLED_ORDER"
    assert len(store.list_orders()) == 1


def test_paper_runner_blocks_when_symbol_exposure_limit_is_exceeded() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("1000"),
            average_entry_price=Decimal("500"),
            stop_protected=True,
            stop_price=Decimal("450"),
        )
    )
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)

    state = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    ).tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "EXPOSURE_LIMIT"


def test_paper_runner_reads_latest_kill_switch_before_ordering() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    )
    store.save_mode_state(
        ModeState(
            mode=RuntimeMode.KILL_SWITCHED,
            live_trading_enabled=False,
            paper_allow_real_order_api=False,
            kill_switch_enabled=True,
        )
    )

    state = runner.tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "KILL_SWITCH_ON"
    assert store.list_orders() == []


def test_paper_runner_never_calls_real_order_or_cancel_api() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-DOGE",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-DOGE"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        ticker_client=RealOrderApiTrap(),
        selected_markets=["KRW-DOGE"],
        price_by_market={"KRW-DOGE": Decimal("100")},
        candle_store=candle_store,
    )

    runner.refresh_markets()
    state = runner.tick()

    assert state.last_action == "PAPER_FILLED"
    assert len(store.list_fills()) == 1


def test_paper_runner_uses_public_ticker_trade_price_for_paper_fill() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-DOGE",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-DOGE"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        ticker_client=FakeTickerClient(),
        top_alt_count=1,
        candle_store=candle_store,
    )

    state = runner.tick()

    assert state.selected_markets == ["KRW-DOGE"]
    assert state.last_action == "PAPER_FILLED"
    assert store.list_fills()[0].price == Decimal("100")


def test_paper_runner_fetches_public_rest_candles_before_signal_evaluation() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-DOGE",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    ticker_client = PublicCandleTickerClient()
    runner = PaperRunner(
        store=store,
        ticker_client=ticker_client,
        top_alt_count=1,
    )

    state = runner.tick()

    assert ticker_client.candle_calls == [("KRW-DOGE", 5, 100), ("KRW-DOGE", 15, 100)]
    assert state.last_action == "PAPER_FILLED"
    assert len(store.list_orders()) == 1


def test_paper_runner_manages_1r_2r_trailing_and_client_side_stop() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
        order_quote_amount_krw=Decimal("50000"),
        fee_rate=Decimal("0"),
    )
    runner.tick()
    position = store.list_positions()[0]
    entry_volume = position.volume
    target1 = position.target1_price
    target2 = position.target2_price
    assert target1 is not None
    assert target2 is not None

    runner.set_market_price("KRW-XRP", target1)
    one_r = runner.tick()
    position = store.list_positions()[0]
    assert one_r.last_action == "PAPER_POSITION_MANAGED"
    assert position.volume == entry_volume * Decimal("0.5")
    assert position.stop_price == position.average_entry_price
    assert position.management_stage == "TOOK_1R"

    runner.set_market_price("KRW-XRP", target2)
    two_r = runner.tick()
    position = store.list_positions()[0]
    assert two_r.last_action == "PAPER_POSITION_MANAGED"
    assert position.volume == entry_volume * Decimal("0.2")
    assert position.trailing_stop_price is not None
    assert position.management_stage == "TRAILING"

    runner.set_market_price("KRW-XRP", position.trailing_stop_price)
    stopped = runner.tick()

    assert stopped.last_action == "PAPER_POSITION_MANAGED"
    assert store.list_positions()[0].volume == Decimal("0.0")
    assert store.list_positions()[0].management_stage == "CLOSED_TRAILING_STOP"


def test_paper_runner_emergency_exits_when_price_gaps_below_stop() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        mode=ModeState(),
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
        order_quote_amount_krw=Decimal("50000"),
        fee_rate=Decimal("0"),
    )
    runner.tick()
    stop_price = store.list_positions()[0].stop_price
    assert stop_price is not None

    runner.set_market_price("KRW-XRP", stop_price - Decimal("10"))
    state = runner.tick()
    position = store.list_positions()[0]

    assert state.last_action == "PAPER_POSITION_MANAGED"
    assert position.volume == Decimal("0.0")
    assert position.management_stage == "CLOSED_EMERGENCY_EXIT"


def test_paper_runner_start_runs_background_ticks_until_stopped() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    runner = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={},
        tick_interval_sec=0.02,
    )

    started = runner.start()
    first_tick = _wait_for_tick_after(runner, started.last_tick_at)
    second_tick = _wait_for_tick_after(runner, first_tick)
    stopped = runner.stop()
    stopped_tick = stopped.last_tick_at
    sleep(0.06)

    assert first_tick is not None
    assert second_tick is not None
    assert second_tick > first_tick
    assert runner.status().running is False
    assert runner.status().last_tick_at == stopped_tick


def _wait_for_tick_after(runner: PaperRunner, previous):
    deadline = monotonic() + 1
    while monotonic() < deadline:
        tick = runner.status().last_tick_at
        if tick is not None and tick != previous:
            return tick
        sleep(0.01)
    raise AssertionError("runner tick did not advance")


def _create_order_in_status(
    store: StateStore,
    *,
    market: str,
    status: OrderStatus,
) -> None:
    state_change = StateChangeRequest(
        request_id="req-existing",
        idempotency_key="idem-existing",
        operator_id="tester",
        reason="blocking order guard",
    )
    order = OrderCoordinator(store).create_entry_order(
        market=market,
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier="client-existing",
        state_change=state_change,
    )
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.SUBMITTING,
        request_id="req-submit",
        idempotency_key="idem-submit",
        operator_id="tester",
        reason="submitting",
    )
    if status is OrderStatus.SUBMITTING:
        return
    if status is OrderStatus.UNKNOWN:
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.UNKNOWN,
            request_id="req-unknown",
            idempotency_key="idem-unknown",
            operator_id="tester",
            reason="timeout",
        )
        return
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.ACCEPTED,
        request_id="req-accepted",
        idempotency_key="idem-accepted",
        operator_id="tester",
        reason="accepted",
    )
    if status is OrderStatus.PARTIALLY_FILLED:
        store.transition_order(
            order_id=order.order_id,
            next_status=OrderStatus.PARTIALLY_FILLED,
            request_id="req-partial",
            idempotency_key="idem-partial",
            operator_id="tester",
            reason="partial",
        )
        return
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.CANCEL_REQUESTED,
        request_id="req-cancel",
        idempotency_key="idem-cancel",
        operator_id="tester",
        reason="cancel requested",
    )
    store.transition_order(
        order_id=order.order_id,
        next_status=OrderStatus.CANCEL_FAILED,
        request_id="req-cancel-failed",
        idempotency_key="idem-cancel-failed",
        operator_id="tester",
        reason="cancel failed",
    )


def ufs_r1_signal_candles(market: str) -> list[Candle]:
    base = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    rows = [
        ("0", "100", "90", "96", "98", "100"),
        ("1", "105", "92", "94", "102", "250"),
        ("2", "130", "110", "125", "112", "400"),
        ("3", "118", "95", "98", "116", "260"),
        ("4", "112", "97", "106", "99", "300"),
    ]
    return [
        Candle(
            market=market,
            timeframe="5m",
            candle_time=base + timedelta(minutes=5 * index),
            open=Decimal(open_),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal(volume),
        )
        for index, (_, high, low, close, open_, volume) in enumerate(rows)
    ]


def uptrend_15m_candles(market: str) -> list[Candle]:
    base = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    rows = [
        ("100", "95", "98"),
        ("110", "100", "108"),
        ("120", "110", "118"),
        ("130", "120", "128"),
    ]
    return [
        Candle(
            market=market,
            timeframe="15m",
            candle_time=base + timedelta(minutes=15 * index),
            open=Decimal(close),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("100"),
        )
        for index, (high, low, close) in enumerate(rows)
    ]
