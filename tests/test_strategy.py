from datetime import UTC, datetime, timedelta
from decimal import Decimal

from haley.market_data import Candle
from haley.strategy import (
    BacktestEngine,
    BacktestLimitOrder,
    CostModel,
    SignalDecision,
    SignalReplayComparison,
    StrategySignal,
    TradePlan,
    UfsR1SignalEngine,
    ZoneState,
    ZoneStatus,
    calculate_atr,
    calculate_regression_channel,
    calculate_ema,
    detect_bullish_ob_candidates,
    detect_bullish_fvg,
    detect_bullish_trap,
    find_confirmed_pivot_highs,
    signal_from_pattern,
)


def candle(
    index: int,
    high: str,
    low: str,
    close: str,
    open_: str | None = None,
    synthetic: bool = False,
) -> Candle:
    return Candle(
        market="KRW-XRP",
        timeframe="1m",
        candle_time=datetime(2026, 5, 31, 0, 0, tzinfo=UTC) + timedelta(minutes=index),
        open=Decimal(close if open_ is None else open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        synthetic=synthetic,
    )


def test_invalidated_zone_cannot_create_signal() -> None:
    zone = ZoneState(
        zone_id="zone-1",
        market="KRW-XRP",
        timeframe="5m",
        lower=Decimal("100"),
        upper=Decimal("110"),
        status=ZoneStatus.INVALIDATED,
    )

    assert zone.can_create_signal is False


def test_signal_replay_comparison_finds_missing_paper_signal() -> None:
    comparison = SignalReplayComparison.compare(
        backtest_signal_ids=["KRW-XRP:2026-06-07T00:00:00"],
        paper_signal_ids=[],
    )

    assert comparison.matched_count == 0
    assert comparison.missing_in_paper == ["KRW-XRP:2026-06-07T00:00:00"]
    assert comparison.extra_in_paper == []


def test_detect_bullish_fvg_uses_three_candles_and_excludes_synthetic() -> None:
    candles = [
        candle(0, high="100", low="90", close="95"),
        candle(1, high="110", low="98", close="105"),
        candle(2, high="120", low="105", close="115"),
    ]
    synthetic = [candles[0], candle(1, high="110", low="98", close="105", synthetic=True), candles[2]]

    zones = detect_bullish_fvg(candles)
    skipped = detect_bullish_fvg(synthetic)

    assert len(zones) == 1
    assert zones[0].lower == Decimal("100")
    assert zones[0].upper == Decimal("105")
    assert skipped == []


def test_find_confirmed_pivot_highs_waits_for_right_candles() -> None:
    candles = [
        candle(0, high="100", low="90", close="95"),
        candle(1, high="110", low="90", close="100"),
        candle(2, high="105", low="90", close="100"),
    ]

    unconfirmed = find_confirmed_pivot_highs(candles[:2], left=1, right=1)
    confirmed = find_confirmed_pivot_highs(candles, left=1, right=1)

    assert unconfirmed == []
    assert len(confirmed) == 1
    assert confirmed[0].confirmed_at == candles[2].candle_time


def test_signal_generation_keeps_hard_block_separate_from_score() -> None:
    blocked = signal_from_pattern(
        market="KRW-XRP",
        pattern_score=90,
        hard_block_reasons=["DATA_STALE"],
    )

    assert blocked == SignalDecision(
        market="KRW-XRP",
        signal_score=90,
        hard_block_pass=False,
        can_create_trade_plan=False,
        reasons=["DATA_STALE"],
    )


def test_calculate_ema_returns_series_without_using_future_values() -> None:
    candles = [
        candle(0, high="100", low="90", close="100"),
        candle(1, high="110", low="90", close="110"),
        candle(2, high="120", low="90", close="120"),
    ]

    ema = calculate_ema(candles, period=2)

    assert ema == [Decimal("100"), Decimal("106.6666666666666666666666667"), Decimal("115.5555555555555555555555556")]


def test_calculate_atr_uses_true_range_series() -> None:
    candles = [
        candle(0, high="100", low="90", close="95"),
        candle(1, high="110", low="94", close="100"),
        candle(2, high="108", low="97", close="105"),
    ]

    atr = calculate_atr(candles, period=2)

    assert atr == [Decimal("10"), Decimal("13"), Decimal("13.5")]


def test_backtest_engine_applies_fee_and_slippage_costs() -> None:
    engine = BacktestEngine(cost_model=CostModel(fee_rate=Decimal("0.0005"), slippage_pct=Decimal("0.001")))

    result = engine.simulate_long(
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quote_amount=Decimal("10000"),
    )

    assert result.entry_fill_price == Decimal("100.100")
    assert result.exit_fill_price == Decimal("109.890")
    assert result.net_pnl == Decimal("967.5329670329670329670329690")


def test_detect_bullish_ob_candidate_uses_last_bearish_before_impulse() -> None:
    candles = [
        candle(0, high="100", low="90", close="95"),
        candle(1, high="98", low="88", close="90", open_="96"),
        candle(2, high="130", low="100", close="125"),
    ]

    zones = detect_bullish_ob_candidates(candles, impulse_min_range=Decimal("20"))

    assert len(zones) == 1
    assert zones[0].lower == Decimal("88")
    assert zones[0].upper == Decimal("98")


def test_detect_bullish_trap_requires_reclaim_within_window() -> None:
    candles = [
        candle(0, high="105", low="99", close="101"),
        candle(1, high="100", low="95", close="97"),
        candle(2, high="104", low="96", close="103"),
    ]

    trap = detect_bullish_trap(candles, level=Decimal("100"), reclaim_window=2)

    assert trap is not None
    assert trap.level == Decimal("100")
    assert trap.reclaimed_at == candles[2].candle_time


def test_calculate_regression_channel_returns_center_and_bands() -> None:
    candles = [
        candle(0, high="101", low="99", close="100"),
        candle(1, high="103", low="101", close="102"),
        candle(2, high="105", low="103", close="104"),
    ]

    channel = calculate_regression_channel(candles)

    assert channel.slope == Decimal("2")
    assert channel.center[-1] == Decimal("104")
    assert channel.upper[-1] == Decimal("105")
    assert channel.lower[-1] == Decimal("103")


def test_backtest_limit_order_partial_fill_tracks_order_status() -> None:
    engine = BacktestEngine(cost_model=CostModel(fee_rate=Decimal("0.0005"), slippage_pct=Decimal("0.001")))
    order = BacktestLimitOrder(
        market="KRW-XRP",
        side="bid",
        limit_price=Decimal("500"),
        volume=Decimal("100"),
    )

    result = engine.simulate_limit_fill(
        order=order,
        available_volume=Decimal("40"),
        trade_price=Decimal("499"),
    )

    assert result.status == "PARTIALLY_FILLED"
    assert result.filled_volume == Decimal("40")
    assert result.remaining_volume == Decimal("60")


def test_backtest_limit_order_no_fill_when_price_does_not_cross() -> None:
    engine = BacktestEngine(cost_model=CostModel(fee_rate=Decimal("0.0005"), slippage_pct=Decimal("0.001")))
    order = BacktestLimitOrder(
        market="KRW-XRP",
        side="bid",
        limit_price=Decimal("500"),
        volume=Decimal("100"),
    )

    result = engine.simulate_limit_fill(
        order=order,
        available_volume=Decimal("100"),
        trade_price=Decimal("501"),
    )

    assert result.status == "ACCEPTED"
    assert result.filled_volume == Decimal("0")


def test_ufs_r1_signal_engine_returns_signal_with_trade_plan_fields() -> None:
    candles = [
        candle(0, high="100", low="90", close="96", open_="98"),
        candle(1, high="105", low="92", close="94", open_="102"),
        candle(2, high="130", low="110", close="125", open_="112"),
        candle(3, high="118", low="95", close="98", open_="116"),
        candle(4, high="112", low="97", close="106", open_="99"),
    ]
    engine = UfsR1SignalEngine()

    signal = engine.evaluate(market="KRW-XRP", candles_5m=candles)
    assert signal == StrategySignal(
        strategy="UFS-R1",
        market="KRW-XRP",
        signal_score=90,
        reasons=[
            "BULLISH_FVG",
            "BULLISH_OB",
            "BULLISH_TRAP",
            "RISK_REWARD_OK",
        ],
        entry_price=Decimal("106"),
        stop_price=Decimal("89.92"),
        target1_price=Decimal("122.08"),
        target2_price=Decimal("138.16"),
        invalidation_conditions=[
            "CLOSE_BELOW_ZONE_LOW",
            "UPPER_FAKE_OUT",
            "DOWNTREND_FILTER",
            "NO_PROGRESS",
        ],
    )

    plan = signal.to_trade_plan(quote_amount=Decimal("50000"))

    assert plan == TradePlan(
        strategy="UFS-R1",
        market="KRW-XRP",
        side="bid",
        order_type="limit",
        quote_amount=Decimal("50000"),
        entry_price=Decimal("106"),
        volume=Decimal("471.6981132075471698113207547"),
        stop_price=Decimal("89.92"),
        target1_price=Decimal("122.08"),
        target2_price=Decimal("138.16"),
        signal_score=90,
        reasons=signal.reasons,
        invalidation_conditions=signal.invalidation_conditions,
    )


def test_ufs_r1_signal_engine_does_not_use_synthetic_for_patterns() -> None:
    candles = [
        candle(0, high="100", low="90", close="96", open_="98"),
        candle(1, high="105", low="92", close="94", open_="102", synthetic=True),
        candle(2, high="130", low="110", close="125", open_="112"),
        candle(3, high="118", low="95", close="98", open_="116"),
        candle(4, high="112", low="97", close="106", open_="99"),
    ]
    engine = UfsR1SignalEngine()

    signal = engine.evaluate(market="KRW-XRP", candles_5m=candles)

    assert signal is None


def test_ufs_r1_signal_engine_blocks_long_below_falling_15m_channel_center() -> None:
    candles = [
        candle(0, high="100", low="90", close="96", open_="98"),
        candle(1, high="105", low="92", close="94", open_="102"),
        candle(2, high="130", low="110", close="125", open_="112"),
        candle(3, high="118", low="95", close="98", open_="116"),
        candle(4, high="112", low="97", close="106", open_="99"),
    ]
    candles_15m = [
        candle(0, high="150", low="145", close="148"),
        candle(1, high="140", low="135", close="138"),
        candle(2, high="130", low="125", close="128"),
        candle(3, high="120", low="115", close="116"),
    ]
    engine = UfsR1SignalEngine()

    signal = engine.evaluate(
        market="KRW-XRP",
        candles_5m=candles,
        candles_15m=candles_15m,
    )

    assert signal is None
