from decimal import Decimal

import pytest

from haley.api_contracts import StateChangeRequest
from haley.domain import OrderSide, OrderStatus, OrderType
from haley.orders import OrderCoordinator
from haley.paper import AveragingDownBlocked, PaperExecutionEngine, PaperPortfolio
from haley.state_store import StateStore


def make_state_change() -> StateChangeRequest:
    return StateChangeRequest(
        request_id="req-paper",
        idempotency_key="idem-paper",
        operator_id="local-user",
        reason="paper test",
    )


def test_paper_buy_fill_updates_virtual_cash_position_and_fee() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    engine = PaperExecutionEngine(store=store, portfolio=portfolio, fee_rate=Decimal("0.0005"))

    fill = engine.buy(
        order_id="order-1",
        market="KRW-XRP",
        quote_amount=Decimal("50000"),
        price=Decimal("500"),
    )

    assert fill.side is OrderSide.BID
    assert fill.volume == Decimal("100")
    assert fill.fee == Decimal("25.0000")
    assert portfolio.cash_krw == Decimal("949975.0000")

    position = store.list_positions()[0]
    assert position.market == "KRW-XRP"
    assert position.volume == Decimal("100")
    assert position.average_entry_price == Decimal("500")
    assert not position.stop_protected


def test_paper_sell_fill_updates_cash_position_and_realized_pnl() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    engine = PaperExecutionEngine(store=store, portfolio=portfolio, fee_rate=Decimal("0.0005"))
    engine.buy(
        order_id="order-1",
        market="KRW-XRP",
        quote_amount=Decimal("50000"),
        price=Decimal("500"),
    )

    fill = engine.sell(
        order_id="order-2",
        market="KRW-XRP",
        volume=Decimal("40"),
        price=Decimal("550"),
    )

    assert fill.side is OrderSide.ASK
    assert fill.fee == Decimal("11.0000")
    assert portfolio.cash_krw == Decimal("971964.0000")

    position = store.list_positions()[0]
    assert position.volume == Decimal("60")
    assert position.average_entry_price == Decimal("500")
    assert position.realized_pnl == Decimal("1989.0000")


def test_paper_execution_engine_never_calls_real_order_api() -> None:
    class RealExchangeTrap:
        def create_order(self) -> None:
            raise AssertionError("real order API must not be called")

    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    engine = PaperExecutionEngine(
        store=store,
        portfolio=portfolio,
        fee_rate=Decimal("0.0005"),
        exchange=RealExchangeTrap(),
        allow_real_order_api=False,
    )

    engine.buy(
        order_id="order-1",
        market="KRW-XRP",
        quote_amount=Decimal("50000"),
        price=Decimal("500"),
    )

    assert len(store.list_fills("order-1")) == 1


def test_paper_partial_buy_fill_locks_cash_and_marks_order_partially_filled() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("50000"),
        volume=Decimal("100"),
        limit_price=Decimal("500"),
        exchange_identifier=None,
        state_change=make_state_change(),
    )
    store.transition_order(
        order.order_id,
        OrderStatus.SUBMITTING,
        "req-submit",
        "idem-submit",
        "local-user",
        "paper submit",
    )
    store.transition_order(
        order.order_id,
        OrderStatus.ACCEPTED,
        "req-accepted",
        "idem-accepted",
        "local-user",
        "paper accepted",
    )
    engine = PaperExecutionEngine(store=store, portfolio=portfolio, fee_rate=Decimal("0.0005"))

    engine.reserve_buy_order(order.order_id)
    fill = engine.fill_buy_order(
        order_id=order.order_id,
        price=Decimal("500"),
        volume=Decimal("40"),
        state_change=make_state_change(),
    )

    assert fill.volume == Decimal("40")
    assert portfolio.locked_cash_krw == Decimal("30015.0000")
    assert portfolio.cash_krw == Decimal("949975.0000")
    assert store.get_order(order.order_id).status is OrderStatus.PARTIALLY_FILLED
    assert store.list_stop_protections("KRW-XRP")[0].market == "KRW-XRP"


def test_paper_full_buy_fill_releases_locked_cash_and_marks_order_filled() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("50000"),
        volume=Decimal("100"),
        limit_price=Decimal("500"),
        exchange_identifier=None,
        state_change=make_state_change(),
    )
    store.transition_order(
        order.order_id,
        OrderStatus.SUBMITTING,
        "req-submit",
        "idem-submit",
        "local-user",
        "paper submit",
    )
    store.transition_order(
        order.order_id,
        OrderStatus.ACCEPTED,
        "req-accepted",
        "idem-accepted",
        "local-user",
        "paper accepted",
    )
    engine = PaperExecutionEngine(store=store, portfolio=portfolio, fee_rate=Decimal("0.0005"))

    engine.reserve_buy_order(order.order_id)
    engine.fill_buy_order(
        order_id=order.order_id,
        price=Decimal("500"),
        volume=Decimal("100"),
        state_change=make_state_change(),
    )

    assert portfolio.locked_cash_krw == Decimal("0.0000")
    assert store.get_order(order.order_id).status is OrderStatus.FILLED


def test_paper_blocks_averaging_down_on_losing_position() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    engine = PaperExecutionEngine(store=store, portfolio=portfolio, fee_rate=Decimal("0.0005"))
    engine.buy(
        order_id="order-1",
        market="KRW-XRP",
        quote_amount=Decimal("50000"),
        price=Decimal("500"),
    )

    with pytest.raises(AveragingDownBlocked, match="KRW-XRP"):
        engine.buy(
            order_id="order-2",
            market="KRW-XRP",
            quote_amount=Decimal("50000"),
            price=Decimal("490"),
        )


def test_paper_portfolio_can_be_saved_loaded_and_reset() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    portfolio.cash_krw = Decimal("900000")
    portfolio.locked_cash_krw = Decimal("50000")

    store.save_paper_portfolio(portfolio)
    saved = store.get_paper_portfolio()

    assert saved.initial_cash_krw == Decimal("1000000")
    assert saved.cash_krw == Decimal("900000")
    assert saved.locked_cash_krw == Decimal("50000")

    saved.reset()
    store.save_paper_portfolio(saved)
    reset = store.get_paper_portfolio()

    assert reset.cash_krw == Decimal("1000000")
    assert reset.locked_cash_krw == Decimal("0")
