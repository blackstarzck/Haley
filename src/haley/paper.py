from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from haley.api_contracts import StateChangeRequest
from haley.domain import Fill, OrderSide, OrderStatus, PositionState, StopProtectionState
from haley.state_store import StateStore


class AveragingDownBlocked(RuntimeError):
    """Raised when PAPER tries to add to a losing position."""


@dataclass
class PaperPortfolio:
    initial_cash_krw: Decimal
    cash_krw: Decimal | None = None
    locked_cash_krw: Decimal = Decimal("0.0000")

    def __post_init__(self) -> None:
        if self.cash_krw is None:
            self.cash_krw = self.initial_cash_krw

    def reset(self) -> None:
        self.cash_krw = self.initial_cash_krw
        self.locked_cash_krw = Decimal("0")


class PaperExecutionEngine:
    def __init__(
        self,
        store: StateStore,
        portfolio: PaperPortfolio,
        fee_rate: Decimal,
        exchange: object | None = None,
        allow_real_order_api: bool = False,
    ) -> None:
        self._store = store
        self._portfolio = portfolio
        self._fee_rate = fee_rate
        self._exchange = exchange
        self._allow_real_order_api = allow_real_order_api

    def buy(
        self,
        order_id: str,
        market: str,
        quote_amount: Decimal,
        price: Decimal,
    ) -> Fill:
        self._guard_real_order_api()
        self._raise_if_averaging_down(market, price)
        volume = quote_amount / price
        fee = quote_amount * self._fee_rate
        fill = Fill(
            fill_id=f"fill_{uuid4().hex}",
            order_id=order_id,
            market=market,
            side=OrderSide.BID,
            price=price,
            volume=volume,
            fee=fee,
            filled_at=datetime.now(UTC),
        )
        self._store.save_fill(fill)
        self._portfolio.cash_krw -= quote_amount + fee
        self._apply_buy_position(fill)
        self._create_stop_watch(fill.market)
        return fill

    def reserve_buy_order(self, order_id: str) -> None:
        order = self._store.get_order(order_id)
        if order.intent.quote_amount is None:
            raise ValueError("quote_amount is required for paper buy reservation")
        fee = order.intent.quote_amount * self._fee_rate
        reserved = order.intent.quote_amount + fee
        self._portfolio.cash_krw -= reserved
        self._portfolio.locked_cash_krw += reserved

    def fill_buy_order(
        self,
        order_id: str,
        price: Decimal,
        volume: Decimal,
        state_change: StateChangeRequest,
    ) -> Fill:
        self._guard_real_order_api()
        order = self._store.get_order(order_id)
        self._raise_if_averaging_down(order.intent.market, price)
        gross = price * volume
        fee = gross * self._fee_rate
        fill = Fill(
            fill_id=f"fill_{uuid4().hex}",
            order_id=order_id,
            market=order.intent.market,
            side=OrderSide.BID,
            price=price,
            volume=volume,
            fee=fee,
            filled_at=datetime.now(UTC),
        )
        self._store.save_fill(fill)
        self._portfolio.locked_cash_krw -= gross + fee
        self._apply_buy_position(fill)
        self._create_stop_watch(fill.market)

        total_filled = sum(item.volume for item in self._store.list_fills(order_id))
        intended_volume = order.intent.volume
        next_status = (
            OrderStatus.FILLED
            if intended_volume is not None and total_filled >= intended_volume
            else OrderStatus.PARTIALLY_FILLED
        )
        self._store.transition_order(
            order_id=order_id,
            next_status=next_status,
            request_id=state_change.request_id,
            idempotency_key=state_change.idempotency_key,
            operator_id=state_change.operator_id,
            reason=state_change.reason,
        )
        return fill

    def sell(
        self,
        order_id: str,
        market: str,
        volume: Decimal,
        price: Decimal,
    ) -> Fill:
        self._guard_real_order_api()
        gross = volume * price
        fee = gross * self._fee_rate
        fill = Fill(
            fill_id=f"fill_{uuid4().hex}",
            order_id=order_id,
            market=market,
            side=OrderSide.ASK,
            price=price,
            volume=volume,
            fee=fee,
            filled_at=datetime.now(UTC),
        )
        self._store.save_fill(fill)
        self._portfolio.cash_krw += gross - fee
        self._apply_sell_position(fill)
        return fill

    def _apply_buy_position(self, fill: Fill) -> None:
        position = _find_position(self._store, fill.market)
        if position is None:
            next_position = PositionState(
                market=fill.market,
                volume=fill.volume,
                average_entry_price=fill.price,
                stop_protected=False,
            )
        else:
            total_volume = position.volume + fill.volume
            total_cost = (
                position.average_entry_price * position.volume
                + fill.price * fill.volume
            )
            next_position = PositionState(
                market=fill.market,
                volume=total_volume,
                average_entry_price=total_cost / total_volume,
                realized_pnl=position.realized_pnl,
                stop_protected=position.stop_protected,
            )
        self._store.upsert_position(next_position)

    def _apply_sell_position(self, fill: Fill) -> None:
        position = _find_position(self._store, fill.market)
        if position is None or position.volume < fill.volume:
            raise ValueError("cannot sell more than paper position volume")
        realized_pnl = (
            position.realized_pnl
            + (fill.price - position.average_entry_price) * fill.volume
            - fill.fee
        )
        self._store.upsert_position(
            PositionState(
                market=fill.market,
                volume=position.volume - fill.volume,
                average_entry_price=position.average_entry_price,
                realized_pnl=realized_pnl,
                stop_protected=position.stop_protected,
            )
        )

    def _guard_real_order_api(self) -> None:
        if self._allow_real_order_api and self._exchange is not None:
            raise RuntimeError("PAPER execution must not call real order API")

    def _raise_if_averaging_down(self, market: str, price: Decimal) -> None:
        position = _find_position(self._store, market)
        if position is not None and position.volume > 0 and price < position.average_entry_price:
            raise AveragingDownBlocked(f"{market} position is losing; averaging down is blocked")

    def _create_stop_watch(self, market: str) -> None:
        position = _find_position(self._store, market)
        if position is None:
            return
        self._store.create_stop_protection(
            StopProtectionState(
                market=market,
                position_volume=position.volume,
                protected=False,
            )
        )


def _find_position(store: StateStore, market: str) -> PositionState | None:
    for position in store.list_positions():
        if position.market == market:
            return position
    return None
