from __future__ import annotations

from decimal import Decimal
from typing import Any

from haley.domain import ModeState, OrderSide, OrderType


class RealOrderGateway:
    def __init__(self, base_url: str, http_client: Any, mode: ModeState) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._mode = mode

    def create_order(
        self,
        *,
        market: str,
        side: OrderSide,
        order_type: OrderType,
        volume: Decimal | None,
        price: Decimal | None,
        identifier: str,
    ) -> dict[str, Any]:
        self._raise_if_locked()
        raise RuntimeError("real order API is not implemented in first release")

    def cancel_order(self, *, identifier: str) -> dict[str, Any]:
        self._raise_if_locked()
        raise RuntimeError("real cancel API is not implemented in first release")

    def _raise_if_locked(self) -> None:
        if not self._mode.allows_real_order_api:
            raise RuntimeError("LIVE trading is disabled")
