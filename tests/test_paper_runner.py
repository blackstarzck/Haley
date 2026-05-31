from decimal import Decimal
from time import monotonic, sleep

from haley.paper import PaperPortfolio
from haley.paper_runner import PaperRunner
from haley.domain import DataQualityState, ModeState, OrderStatus, ReconciliationState, ReconciliationStatus
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


def test_paper_runner_tick_creates_paper_order_fill_and_position_after_risk_passes() -> None:
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
        fee_rate=Decimal("0.0005"),
    )

    state = runner.tick()

    order = store.list_orders()[0]
    portfolio = store.get_paper_portfolio()

    assert state.last_action == "PAPER_FILLED"
    assert state.last_block_reason is None
    assert order.status is OrderStatus.FILLED
    assert len(store.list_fills(order.order_id)) == 1
    assert store.list_positions()[0].market == "KRW-XRP"
    assert store.list_stop_protections("KRW-XRP")[0].protected is False
    assert portfolio.cash_krw == Decimal("949975.0000")


def test_paper_runner_never_calls_real_order_or_cancel_api() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-DOGE",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    runner = PaperRunner(
        store=store,
        ticker_client=RealOrderApiTrap(),
        selected_markets=["KRW-DOGE"],
        price_by_market={"KRW-DOGE": Decimal("100")},
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
    runner = PaperRunner(
        store=store,
        ticker_client=FakeTickerClient(),
        top_alt_count=1,
    )

    state = runner.tick()

    assert state.selected_markets == ["KRW-DOGE"]
    assert state.last_action == "PAPER_FILLED"
    assert store.list_fills()[0].price == Decimal("100")


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
