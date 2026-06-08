from decimal import Decimal

import pytest

from haley.domain import ModeState, OrderSide, OrderType, RuntimeMode
from haley.order_gateway import RealOrderGateway


class SpyHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> object:
        self.calls.append(("POST", url, kwargs))
        raise AssertionError("real order HTTP call must not happen")

    def delete(self, url: str, **kwargs: object) -> object:
        self.calls.append(("DELETE", url, kwargs))
        raise AssertionError("real cancel HTTP call must not happen")


@pytest.mark.parametrize(
    "mode",
    [
        ModeState(mode=RuntimeMode.PAPER, paper_allow_real_order_api=False),
        ModeState(mode=RuntimeMode.DRY_RUN),
        ModeState(mode=RuntimeMode.RECOVERY_ONLY),
        ModeState(mode=RuntimeMode.KILL_SWITCHED, kill_switch_enabled=True),
        ModeState(mode=RuntimeMode.LIVE, live_trading_enabled=False),
    ],
)
def test_real_order_gateway_never_calls_http_when_locked(mode: ModeState) -> None:
    http = SpyHttpClient()
    gateway = RealOrderGateway(
        base_url="https://api.upbit.com",
        http_client=http,
        mode=mode,
    )

    with pytest.raises(RuntimeError, match="LIVE trading is disabled"):
        gateway.create_order(
            market="KRW-XRP",
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            volume=Decimal("10"),
            price=Decimal("500"),
            identifier="client-1",
        )

    assert http.calls == []


def test_real_cancel_gateway_never_calls_http_when_locked() -> None:
    http = SpyHttpClient()
    gateway = RealOrderGateway(
        base_url="https://api.upbit.com",
        http_client=http,
        mode=ModeState(),
    )

    with pytest.raises(RuntimeError, match="LIVE trading is disabled"):
        gateway.cancel_order(identifier="client-1")

    assert http.calls == []
