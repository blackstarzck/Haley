from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from haley.api_contracts import StateChangeRequest
from haley.domain import Fill, OrderSide, OrderStatus, PositionState, StopProtectionState
from haley.state_store import StateStore


_KRW_RESIDUE_TOLERANCE = Decimal("0.00000001")


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
        self.locked_cash_krw = _zero_small_residue(self.locked_cash_krw)

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

    def calculate_reference_price_gap(
        self,
        paper_fill_price: Decimal,
        reference_price: Decimal,
    ) -> Decimal:
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")
        return (paper_fill_price - reference_price) / reference_price

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
        if self._portfolio.cash_krw < quote_amount + fee:
            raise ValueError("insufficient paper cash")
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
        if self._portfolio.cash_krw < reserved:
            raise ValueError("insufficient paper cash")
        self._portfolio.cash_krw -= reserved
        self._portfolio.locked_cash_krw += reserved

    def fill_buy_order(
        self,
        order_id: str,
        price: Decimal,
        volume: Decimal,
        state_change: StateChangeRequest,
        stop_price: Decimal | None = None,
        target1_price: Decimal | None = None,
        target2_price: Decimal | None = None,
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
        self._portfolio.locked_cash_krw = _zero_small_residue(
            self._portfolio.locked_cash_krw
        )
        self._apply_buy_position(
            fill,
            stop_price=stop_price,
            target1_price=target1_price,
            target2_price=target2_price,
        )
        self._create_stop_watch(fill.market, stop_price=stop_price)

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

    def manage_position(self, market: str, price: Decimal) -> str | None:
        self._guard_real_order_api()
        position = _find_position(self._store, market)
        if position is None or position.volume <= 0:
            return None

        unrealized = (price - position.average_entry_price) * position.volume
        position = PositionState(
            market=position.market,
            volume=position.volume,
            average_entry_price=position.average_entry_price,
            realized_pnl=position.realized_pnl,
            unrealized_pnl=unrealized,
            stop_protected=position.stop_protected,
            stop_price=position.stop_price,
            target1_price=position.target1_price,
            target2_price=position.target2_price,
            trailing_stop_price=position.trailing_stop_price,
            management_stage=position.management_stage,
        )
        self._store.upsert_position(position)

        if position.stop_price is not None and price <= position.stop_price:
            self.sell(f"paper_stop_{market}", market, position.volume, price)
            stage = (
                "CLOSED_EMERGENCY_EXIT"
                if price < position.stop_price
                else "CLOSED_STOP"
            )
            self._set_position_management(
                market=market,
                price=price,
                stage=stage,
                stop_price=position.stop_price,
                trailing_stop_price=position.trailing_stop_price,
            )
            return "EMERGENCY_EXIT" if stage == "CLOSED_EMERGENCY_EXIT" else "CLIENT_SIDE_STOP"

        if (
            position.management_stage == "OPEN"
            and position.target1_price is not None
            and price >= position.target1_price
        ):
            self.sell(
                f"paper_take_1r_{market}",
                market,
                position.volume * Decimal("0.5"),
                price,
            )
            self._set_position_management(
                market=market,
                price=price,
                stage="TOOK_1R",
                stop_price=position.average_entry_price,
                trailing_stop_price=None,
            )
            return "TAKE_PROFIT_1R"

        if (
            position.management_stage == "TOOK_1R"
            and position.target2_price is not None
            and price >= position.target2_price
        ):
            sell_volume = position.volume * Decimal("0.6")
            self.sell(f"paper_take_2r_{market}", market, sell_volume, price)
            unit_risk = (
                position.average_entry_price - position.stop_price
                if position.stop_price is not None
                else price - position.average_entry_price
            )
            trailing_stop = price - max(unit_risk, Decimal("0")) * Decimal("0.5")
            self._set_position_management(
                market=market,
                price=price,
                stage="TRAILING",
                stop_price=position.stop_price,
                trailing_stop_price=trailing_stop,
            )
            return "TAKE_PROFIT_2R"

        if (
            position.management_stage == "TRAILING"
            and position.trailing_stop_price is not None
            and price <= position.trailing_stop_price
        ):
            self.sell(f"paper_trailing_stop_{market}", market, position.volume, price)
            self._set_position_management(
                market=market,
                price=price,
                stage="CLOSED_TRAILING_STOP",
                stop_price=position.stop_price,
                trailing_stop_price=position.trailing_stop_price,
            )
            return "TRAILING_STOP"

        return None

    def _apply_buy_position(
        self,
        fill: Fill,
        stop_price: Decimal | None = None,
        target1_price: Decimal | None = None,
        target2_price: Decimal | None = None,
    ) -> None:
        position = _find_position(self._store, fill.market)
        protected = stop_price is not None
        if position is None:
            next_position = PositionState(
                market=fill.market,
                volume=fill.volume,
                average_entry_price=fill.price,
                stop_protected=protected,
                stop_price=stop_price,
                target1_price=target1_price,
                target2_price=target2_price,
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
                unrealized_pnl=position.unrealized_pnl,
                stop_protected=position.stop_protected or protected,
                stop_price=stop_price or position.stop_price,
                target1_price=target1_price or position.target1_price,
                target2_price=target2_price or position.target2_price,
                trailing_stop_price=position.trailing_stop_price,
                management_stage=position.management_stage,
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
                unrealized_pnl=Decimal("0"),
                stop_protected=position.stop_protected,
                stop_price=position.stop_price,
                target1_price=position.target1_price,
                target2_price=position.target2_price,
                trailing_stop_price=position.trailing_stop_price,
                management_stage=position.management_stage,
            )
        )

    def _guard_real_order_api(self) -> None:
        if self._allow_real_order_api and self._exchange is not None:
            raise RuntimeError("PAPER execution must not call real order API")

    def _raise_if_averaging_down(self, market: str, price: Decimal) -> None:
        position = _find_position(self._store, market)
        if position is not None and position.volume > 0 and price < position.average_entry_price:
            raise AveragingDownBlocked(f"{market} position is losing; averaging down is blocked")

    def _create_stop_watch(self, market: str, stop_price: Decimal | None = None) -> None:
        position = _find_position(self._store, market)
        if position is None:
            return
        self._store.create_stop_protection(
            StopProtectionState(
                market=market,
                position_volume=position.volume,
                protected=stop_price is not None,
                stop_price=stop_price,
            )
        )

    def _set_position_management(
        self,
        market: str,
        price: Decimal,
        stage: str,
        stop_price: Decimal | None,
        trailing_stop_price: Decimal | None,
    ) -> None:
        position = _find_position(self._store, market)
        if position is None:
            return
        self._store.upsert_position(
            PositionState(
                market=position.market,
                volume=position.volume,
                average_entry_price=position.average_entry_price,
                realized_pnl=position.realized_pnl,
                unrealized_pnl=(price - position.average_entry_price) * position.volume,
                stop_protected=position.volume > 0 and stop_price is not None,
                stop_price=stop_price,
                target1_price=position.target1_price,
                target2_price=position.target2_price,
                trailing_stop_price=trailing_stop_price,
                management_stage=stage,
            )
        )


def _find_position(store: StateStore, market: str) -> PositionState | None:
    for position in store.list_positions():
        if position.market == market:
            return position
    return None


def _zero_small_residue(value: Decimal) -> Decimal:
    if abs(value) <= _KRW_RESIDUE_TOLERANCE:
        return Decimal("0")
    return value
