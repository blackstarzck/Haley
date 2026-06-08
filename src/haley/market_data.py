from __future__ import annotations

from dataclasses import dataclass
from collections.abc import AsyncIterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from haley.domain import DataQualityState


UPBIT_PUBLIC_WEBSOCKET_URL = "wss://api.upbit.com/websocket/v1"


@dataclass(frozen=True)
class Candle:
    market: str
    timeframe: str
    candle_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    synthetic: bool = False

    @property
    def key(self) -> tuple[str, str, datetime]:
        return (self.market, self.timeframe, self.candle_time)

    @property
    def can_feed_indicators(self) -> bool:
        return True

    @property
    def can_create_pattern(self) -> bool:
        return not self.synthetic


@dataclass(frozen=True)
class CandleUseDecision:
    usable: bool
    signal_eligible_at: datetime


@dataclass(frozen=True)
class CandleUsePolicy:
    candle_grace_ms: int

    def evaluate(self, *, closed_at: datetime, now: datetime) -> CandleUseDecision:
        eligible_at = closed_at + timedelta(milliseconds=self.candle_grace_ms)
        return CandleUseDecision(
            usable=now >= eligible_at,
            signal_eligible_at=eligible_at,
        )


class CandleStore:
    def __init__(self) -> None:
        self._candles: dict[tuple[str, str, datetime], Candle] = {}

    def upsert(self, candle: Candle) -> None:
        self._candles[candle.key] = candle

    def list(self, market: str, timeframe: str) -> list[Candle]:
        return sorted(
            [
                candle
                for candle in self._candles.values()
                if candle.market == market and candle.timeframe == timeframe
            ],
            key=lambda candle: candle.candle_time,
        )


class MarketDataCollector:
    def __init__(self, candle_store: CandleStore) -> None:
        self._candle_store = candle_store

    async def collect_candles(self, source: AsyncIterable[dict[str, object]]) -> None:
        async for message in source:
            message_type = str(message.get("type", ""))
            if message_type.startswith("candle."):
                self._candle_store.upsert(parse_upbit_candle_message(message))


@dataclass(frozen=True)
class DataQualityMonitor:
    stale_timeout_ms: int
    price_mismatch_pct: Decimal

    def evaluate(
        self,
        market: str,
        now: datetime,
        last_ws_received_at: datetime | None,
        rest_price: Decimal | None,
        websocket_price: Decimal | None,
        market_warning: bool = False,
        orderbook_gap: bool = False,
        last_ticker_received_at: datetime | None = None,
        last_trade_received_at: datetime | None = None,
        last_orderbook_received_at: datetime | None = None,
        last_candle_received_at: datetime | None = None,
    ) -> DataQualityState:
        feed_times = [
            item
            for item in (
                last_ticker_received_at,
                last_trade_received_at,
                last_orderbook_received_at,
                last_candle_received_at,
            )
            if item is not None
        ]
        stale = (
            last_ws_received_at is None
            or (now - last_ws_received_at).total_seconds() * 1000 > self.stale_timeout_ms
            or any(
                (now - feed_time).total_seconds() * 1000 > self.stale_timeout_ms
                for feed_time in feed_times
            )
        )
        mismatch = _price_mismatch(
            rest_price=rest_price,
            websocket_price=websocket_price,
            threshold_pct=self.price_mismatch_pct,
        )
        return DataQualityState(
            stale=stale,
            rest_ws_mismatch=mismatch,
            market_warning=market_warning,
            orderbook_gap=orderbook_gap,
            last_ws_received_at=last_ws_received_at,
            last_ticker_received_at=last_ticker_received_at,
            last_trade_received_at=last_trade_received_at,
            last_orderbook_received_at=last_orderbook_received_at,
            last_candle_received_at=last_candle_received_at,
        )


def build_upbit_websocket_subscription(
    markets: list[str], data_types: list[str]
) -> list[dict[str, object]]:
    return [
        {"ticket": f"haley-{uuid4().hex}"},
        *[{"type": data_type, "codes": markets} for data_type in data_types],
    ]


def select_top_krw_alt_markets(
    tickers: list[dict[str, object]],
    count: int,
    include_major_markets: bool = False,
) -> list[str]:
    excluded = set() if include_major_markets else {"KRW-BTC", "KRW-ETH"}
    candidates = [
        ticker
        for ticker in tickers
        if str(ticker["market"]).startswith("KRW-")
        and str(ticker["market"]) not in excluded
    ]
    ranked = sorted(
        candidates,
        key=lambda item: Decimal(str(item.get("acc_trade_price_24h", "0"))),
        reverse=True,
    )
    return [str(item["market"]) for item in ranked[:count]]


def market_event_to_data_quality(payload: dict[str, object]) -> DataQualityState:
    market_event = payload.get("market_event", {})
    if not isinstance(market_event, dict):
        market_event = {}
    caution = market_event.get("caution", {})
    caution_active = isinstance(caution, dict) and any(bool(value) for value in caution.values())
    return DataQualityState(
        stale=False,
        rest_ws_mismatch=False,
        market_warning=bool(market_event.get("warning")) or caution_active,
    )


def parse_upbit_candle_message(message: dict[str, object]) -> Candle:
    message_type = str(message["type"])
    timeframe = message_type.split(".", 1)[1]
    candle_time = datetime.fromisoformat(
        f"{message['candle_date_time_utc']}+00:00"
    ).astimezone(UTC)
    return Candle(
        market=str(message["code"]),
        timeframe=timeframe,
        candle_time=candle_time,
        open=Decimal(str(message["opening_price"])),
        high=Decimal(str(message["high_price"])),
        low=Decimal(str(message["low_price"])),
        close=Decimal(str(message["trade_price"])),
        volume=Decimal(str(message["candle_acc_trade_volume"])),
    )


def parse_upbit_rest_minute_candle(
    market: str,
    unit: int,
    payload: dict[str, object],
) -> Candle:
    candle_time = datetime.fromisoformat(
        f"{payload['candle_date_time_utc']}+00:00"
    ).astimezone(UTC)
    return Candle(
        market=market,
        timeframe=f"{unit}m",
        candle_time=candle_time,
        open=Decimal(str(payload["opening_price"])),
        high=Decimal(str(payload["high_price"])),
        low=Decimal(str(payload["low_price"])),
        close=Decimal(str(payload["trade_price"])),
        volume=Decimal(str(payload["candle_acc_trade_volume"])),
    )


def _price_mismatch(
    rest_price: Decimal | None,
    websocket_price: Decimal | None,
    threshold_pct: Decimal,
) -> bool:
    if rest_price is None or websocket_price is None or websocket_price == 0:
        return False
    return abs(rest_price - websocket_price) / websocket_price > threshold_pct
