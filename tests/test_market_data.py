import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from haley.market_data import (
    Candle,
    CandleStore,
    DataQualityMonitor,
    MarketDataCollector,
    build_upbit_websocket_subscription,
    market_event_to_data_quality,
    parse_upbit_candle_message,
    select_top_krw_alt_markets,
)


def test_candle_store_upserts_same_market_timeframe_and_time() -> None:
    store = CandleStore()
    candle_time = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)

    store.upsert(
        Candle(
            market="KRW-XRP",
            timeframe="1m",
            candle_time=candle_time,
            open=Decimal("500"),
            high=Decimal("510"),
            low=Decimal("490"),
            close=Decimal("505"),
            volume=Decimal("1000"),
        )
    )
    store.upsert(
        Candle(
            market="KRW-XRP",
            timeframe="1m",
            candle_time=candle_time,
            open=Decimal("500"),
            high=Decimal("520"),
            low=Decimal("480"),
            close=Decimal("515"),
            volume=Decimal("1500"),
        )
    )

    candles = store.list("KRW-XRP", "1m")
    assert len(candles) == 1
    assert candles[0].high == Decimal("520")
    assert candles[0].close == Decimal("515")


def test_synthetic_candle_can_feed_indicators_but_not_patterns() -> None:
    candle = Candle(
        market="KRW-XRP",
        timeframe="1m",
        candle_time=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        open=Decimal("500"),
        high=Decimal("500"),
        low=Decimal("500"),
        close=Decimal("500"),
        volume=Decimal("0"),
        synthetic=True,
    )

    assert candle.can_feed_indicators
    assert not candle.can_create_pattern


def test_data_quality_monitor_detects_stale_and_price_mismatch() -> None:
    monitor = DataQualityMonitor(stale_timeout_ms=5000, price_mismatch_pct=Decimal("0.01"))
    now = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)

    stale = monitor.evaluate(
        market="KRW-XRP",
        now=now,
        last_ws_received_at=now - timedelta(milliseconds=6000),
        rest_price=Decimal("500"),
        websocket_price=Decimal("500"),
    )
    mismatch = monitor.evaluate(
        market="KRW-XRP",
        now=now,
        last_ws_received_at=now,
        rest_price=Decimal("510"),
        websocket_price=Decimal("500"),
    )

    assert stale.stale
    assert not stale.rest_ws_mismatch
    assert mismatch.rest_ws_mismatch


def test_build_upbit_websocket_subscription_uses_public_quotation_types() -> None:
    payload = build_upbit_websocket_subscription(
        markets=["KRW-XRP", "KRW-ADA"],
        data_types=["ticker", "trade", "orderbook", "candle.1m"],
    )

    assert payload[0]["ticket"].startswith("haley-")
    assert payload[1:] == [
        {"type": "ticker", "codes": ["KRW-XRP", "KRW-ADA"]},
        {"type": "trade", "codes": ["KRW-XRP", "KRW-ADA"]},
        {"type": "orderbook", "codes": ["KRW-XRP", "KRW-ADA"]},
        {"type": "candle.1m", "codes": ["KRW-XRP", "KRW-ADA"]},
    ]


def test_select_top_krw_alt_markets_excludes_non_krw_and_majors_by_default() -> None:
    tickers = [
        {"market": "KRW-BTC", "acc_trade_price_24h": "900"},
        {"market": "KRW-ETH", "acc_trade_price_24h": "800"},
        {"market": "BTC-XRP", "acc_trade_price_24h": "1000"},
        {"market": "KRW-XRP", "acc_trade_price_24h": "700"},
        {"market": "KRW-ADA", "acc_trade_price_24h": "600"},
        {"market": "KRW-DOGE", "acc_trade_price_24h": "650"},
    ]

    selected = select_top_krw_alt_markets(tickers, count=2, include_major_markets=False)

    assert selected == ["KRW-XRP", "KRW-DOGE"]


def test_market_event_warning_or_caution_blocks_new_entry() -> None:
    state = market_event_to_data_quality(
        {
            "market": "KRW-XRP",
            "market_event": {
                "warning": True,
                "caution": {"PRICE_FLUCTUATIONS": True},
            },
        }
    )

    assert state.market_warning
    assert not state.allows_new_entry


def test_parse_upbit_candle_message_to_candle() -> None:
    candle = parse_upbit_candle_message(
        {
            "type": "candle.1m",
            "code": "KRW-XRP",
            "candle_date_time_utc": "2026-05-31T00:00:00",
            "opening_price": 500,
            "high_price": 510,
            "low_price": 490,
            "trade_price": 505,
            "candle_acc_trade_volume": 123.45,
        }
    )

    assert candle.market == "KRW-XRP"
    assert candle.timeframe == "1m"
    assert candle.close == Decimal("505")


def test_market_data_collector_upserts_candles_from_async_source() -> None:
    async def source():
        yield {
            "type": "candle.1m",
            "code": "KRW-XRP",
            "candle_date_time_utc": "2026-05-31T00:00:00",
            "opening_price": 500,
            "high_price": 510,
            "low_price": 490,
            "trade_price": 505,
            "candle_acc_trade_volume": 123,
        }

    store = CandleStore()
    collector = MarketDataCollector(candle_store=store)

    asyncio.run(collector.collect_candles(source()))

    assert store.list("KRW-XRP", "1m")[0].close == Decimal("505")
