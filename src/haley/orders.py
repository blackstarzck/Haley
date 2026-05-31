from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from haley.api_contracts import StateChangeRequest
from haley.domain import (
    OrderIntent,
    OrderSide,
    OrderState,
    OrderStatus,
    OrderType,
    blocks_new_entry_statuses,
)
from haley.state_store import StateStore


class DuplicateMarketOrderError(RuntimeError):
    """Raised when an unsettled order blocks a same-market new entry."""


class OrderCoordinator:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    def create_entry_order(
        self,
        market: str,
        side: OrderSide,
        order_type: OrderType,
        quote_amount: Decimal | None,
        volume: Decimal | None,
        limit_price: Decimal | None,
        exchange_identifier: str | None,
        state_change: StateChangeRequest,
    ) -> OrderState:
        self._raise_if_market_blocked(market)
        client_order_key = _new_client_order_key(market)
        intent = OrderIntent(
            client_order_key=client_order_key,
            exchange_identifier=exchange_identifier,
            market=market,
            side=side,
            order_type=order_type,
            quote_amount=quote_amount,
            volume=volume,
            limit_price=limit_price,
            request_hash=_request_hash(
                market=market,
                side=side,
                order_type=order_type,
                quote_amount=quote_amount,
                volume=volume,
                limit_price=limit_price,
            ),
            created_at=datetime.now(UTC),
        )
        order_id = self._store.create_order(intent)
        return self._store.get_order(order_id)

    def record_submit_timeout(
        self, order_id: str, state_change: StateChangeRequest
    ) -> OrderState:
        return self._store.transition_order(
            order_id=order_id,
            next_status=OrderStatus.UNKNOWN,
            request_id=state_change.request_id,
            idempotency_key=state_change.idempotency_key,
            operator_id=state_change.operator_id,
            reason=state_change.reason,
        )

    def _raise_if_market_blocked(self, market: str) -> None:
        blocking_orders = self._store.list_orders_for_market(
            market, statuses=blocks_new_entry_statuses()
        )
        if blocking_orders:
            statuses = ", ".join(order.status.value for order in blocking_orders)
            raise DuplicateMarketOrderError(
                f"{market} has unsettled order status: {statuses}"
            )


def _new_client_order_key(market: str) -> str:
    normalized_market = market.replace("-", "_").lower()
    return f"client_{normalized_market}_{uuid4().hex}"


def _request_hash(
    market: str,
    side: OrderSide,
    order_type: OrderType,
    quote_amount: Decimal | None,
    volume: Decimal | None,
    limit_price: Decimal | None,
) -> str:
    payload = {
        "market": market,
        "side": side.value,
        "order_type": order_type.value,
        "quote_amount": None if quote_amount is None else str(quote_amount),
        "volume": None if volume is None else str(volume),
        "limit_price": None if limit_price is None else str(limit_price),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
