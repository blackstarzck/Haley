from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from haley.market_data import Candle


class ZoneStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FILLED = "FILLED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ZoneState:
    zone_id: str
    market: str
    timeframe: str
    lower: Decimal
    upper: Decimal
    status: ZoneStatus

    @property
    def can_create_signal(self) -> bool:
        return self.status is ZoneStatus.ACTIVE


@dataclass(frozen=True)
class FvgZone:
    market: str
    timeframe: str
    lower: Decimal
    upper: Decimal
    created_at: datetime


@dataclass(frozen=True)
class ObZone:
    market: str
    timeframe: str
    lower: Decimal
    upper: Decimal
    created_at: datetime


@dataclass(frozen=True)
class TrapSignal:
    market: str
    timeframe: str
    level: Decimal
    swept_at: datetime
    reclaimed_at: datetime


@dataclass(frozen=True)
class RegressionChannel:
    slope: Decimal
    center: list[Decimal]
    upper: list[Decimal]
    lower: list[Decimal]


@dataclass(frozen=True)
class PivotHigh:
    market: str
    timeframe: str
    price: Decimal
    pivot_time: datetime
    confirmed_at: datetime


@dataclass(frozen=True)
class SignalDecision:
    market: str
    signal_score: int
    hard_block_pass: bool
    can_create_trade_plan: bool
    reasons: list[str]


@dataclass(frozen=True)
class StrategySignal:
    strategy: str
    market: str
    signal_score: int
    reasons: list[str]
    entry_price: Decimal
    stop_price: Decimal
    target1_price: Decimal
    target2_price: Decimal
    invalidation_conditions: list[str]

    def to_trade_plan(self, quote_amount: Decimal) -> TradePlan:
        return TradePlan(
            strategy=self.strategy,
            market=self.market,
            side="bid",
            order_type="limit",
            quote_amount=quote_amount,
            entry_price=self.entry_price,
            volume=quote_amount / self.entry_price,
            stop_price=self.stop_price,
            target1_price=self.target1_price,
            target2_price=self.target2_price,
            signal_score=self.signal_score,
            reasons=list(self.reasons),
            invalidation_conditions=list(self.invalidation_conditions),
        )


@dataclass(frozen=True)
class TradePlan:
    strategy: str
    market: str
    side: str
    order_type: str
    quote_amount: Decimal
    entry_price: Decimal
    volume: Decimal
    stop_price: Decimal
    target1_price: Decimal
    target2_price: Decimal
    signal_score: int
    reasons: list[str]
    invalidation_conditions: list[str]


@dataclass(frozen=True)
class CostModel:
    fee_rate: Decimal
    slippage_pct: Decimal


@dataclass(frozen=True)
class BacktestResult:
    entry_fill_price: Decimal
    exit_fill_price: Decimal
    volume: Decimal
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal


@dataclass(frozen=True)
class BacktestLimitOrder:
    market: str
    side: str
    limit_price: Decimal
    volume: Decimal


@dataclass(frozen=True)
class BacktestOrderFillResult:
    status: str
    filled_volume: Decimal
    remaining_volume: Decimal


@dataclass(frozen=True)
class SignalReplayComparison:
    matched_count: int
    missing_in_paper: list[str]
    extra_in_paper: list[str]

    @classmethod
    def compare(
        cls,
        *,
        backtest_signal_ids: list[str],
        paper_signal_ids: list[str],
    ) -> SignalReplayComparison:
        backtest = set(backtest_signal_ids)
        paper = set(paper_signal_ids)
        return cls(
            matched_count=len(backtest & paper),
            missing_in_paper=sorted(backtest - paper),
            extra_in_paper=sorted(paper - backtest),
        )


class BacktestEngine:
    def __init__(self, cost_model: CostModel) -> None:
        self._cost_model = cost_model

    def simulate_long(
        self, entry_price: Decimal, exit_price: Decimal, quote_amount: Decimal
    ) -> BacktestResult:
        entry_fill_price = entry_price * (Decimal("1") + self._cost_model.slippage_pct)
        exit_fill_price = exit_price * (Decimal("1") - self._cost_model.slippage_pct)
        volume = quote_amount / entry_fill_price
        entry_fee = quote_amount * self._cost_model.fee_rate
        exit_gross = volume * exit_fill_price
        exit_fee = exit_gross * self._cost_model.fee_rate
        gross_pnl = exit_gross - quote_amount
        fees = entry_fee + exit_fee
        return BacktestResult(
            entry_fill_price=entry_fill_price,
            exit_fill_price=exit_fill_price,
            volume=volume,
            gross_pnl=gross_pnl,
            fees=fees,
            net_pnl=gross_pnl - fees,
        )

    def simulate_limit_fill(
        self,
        order: BacktestLimitOrder,
        available_volume: Decimal,
        trade_price: Decimal,
    ) -> BacktestOrderFillResult:
        crosses = (
            trade_price <= order.limit_price
            if order.side == "bid"
            else trade_price >= order.limit_price
        )
        if not crosses:
            return BacktestOrderFillResult(
                status="ACCEPTED",
                filled_volume=Decimal("0"),
                remaining_volume=order.volume,
            )
        filled = min(order.volume, available_volume)
        remaining = order.volume - filled
        return BacktestOrderFillResult(
            status="FILLED" if remaining == 0 else "PARTIALLY_FILLED",
            filled_volume=filled,
            remaining_volume=remaining,
        )


class UfsR1SignalEngine:
    def __init__(
        self,
        reclaim_window: int = 2,
        min_risk_reward: Decimal = Decimal("1.5"),
    ) -> None:
        self._reclaim_window = reclaim_window
        self._min_risk_reward = min_risk_reward

    def evaluate(
        self,
        market: str,
        candles_5m: list[Candle],
        candles_15m: list[Candle] | None = None,
    ) -> StrategySignal | None:
        if len(candles_5m) < 5:
            return None
        if candles_15m and not _trend_filter_allows_long(candles_15m):
            return None

        fvg_zones = detect_bullish_fvg(candles_5m)
        ob_zones = detect_bullish_ob_candidates(
            candles_5m,
            impulse_min_range=_latest_positive_atr(candles_5m) * Decimal("0.5"),
        )
        if not fvg_zones or not ob_zones:
            return None

        fvg = fvg_zones[-1]
        ob = ob_zones[-1]
        if not _zones_overlap_enough(fvg.lower, fvg.upper, ob.lower, ob.upper):
            return None

        support = max(fvg.lower, ob.lower)
        zone_created_at = max(fvg.created_at, ob.created_at)
        post_zone_candles = [
            candle for candle in candles_5m if candle.candle_time >= zone_created_at
        ]
        trap = detect_bullish_trap(
            post_zone_candles,
            level=support,
            reclaim_window=self._reclaim_window,
        )
        if trap is None:
            return None

        entry = candles_5m[-1].close
        atr = _latest_positive_atr(candles_5m)
        fakeout_low = min(
            candle.low
            for candle in candles_5m
            if trap.swept_at <= candle.candle_time <= trap.reclaimed_at
        )
        stop = min(fakeout_low, ob.lower, fvg.lower) - atr * Decimal("0.1")
        unit_risk = entry - stop
        if unit_risk <= 0:
            return None

        target1 = entry + unit_risk
        target2 = entry + unit_risk * Decimal("2")
        risk_reward = (target2 - entry) / unit_risk
        if risk_reward < self._min_risk_reward:
            return None

        return StrategySignal(
            strategy="UFS-R1",
            market=market,
            signal_score=90,
            reasons=[
                "BULLISH_FVG",
                "BULLISH_OB",
                "BULLISH_TRAP",
                "RISK_REWARD_OK",
            ],
            entry_price=entry,
            stop_price=stop,
            target1_price=target1,
            target2_price=target2,
            invalidation_conditions=[
                "CLOSE_BELOW_ZONE_LOW",
                "UPPER_FAKE_OUT",
                "DOWNTREND_FILTER",
                "NO_PROGRESS",
            ],
        )


def calculate_ema(candles: list[Candle], period: int) -> list[Decimal]:
    if not candles:
        return []
    multiplier = Decimal("2") / Decimal(period + 1)
    values = [candles[0].close]
    for item in candles[1:]:
        values.append((item.close - values[-1]) * multiplier + values[-1])
    return values


def calculate_atr(candles: list[Candle], period: int) -> list[Decimal]:
    if not candles:
        return []
    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for item in candles:
        if previous_close is None:
            true_range = item.high - item.low
        else:
            true_range = max(
                item.high - item.low,
                abs(item.high - previous_close),
                abs(item.low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = item.close

    atr: list[Decimal] = []
    for index, true_range in enumerate(true_ranges):
        start = max(0, index - period + 1)
        window = true_ranges[start : index + 1]
        atr.append(sum(window) / Decimal(len(window)))
    return atr


def detect_bullish_fvg(candles: list[Candle]) -> list[FvgZone]:
    zones: list[FvgZone] = []
    for index in range(2, len(candles)):
        first = candles[index - 2]
        middle = candles[index - 1]
        third = candles[index]
        if not (
            first.can_create_pattern
            and middle.can_create_pattern
            and third.can_create_pattern
        ):
            continue
        if third.low > first.high:
            zones.append(
                FvgZone(
                    market=third.market,
                    timeframe=third.timeframe,
                    lower=first.high,
                    upper=third.low,
                    created_at=third.candle_time,
                )
            )
    return zones


def detect_bullish_ob_candidates(
    candles: list[Candle], impulse_min_range: Decimal
) -> list[ObZone]:
    zones: list[ObZone] = []
    for index in range(1, len(candles)):
        previous = candles[index - 1]
        current = candles[index]
        current_range = current.high - current.low
        previous_bearish = previous.close < previous.open
        impulse_up = current.close > previous.high and current_range >= impulse_min_range
        if previous.can_create_pattern and current.can_create_pattern and previous_bearish and impulse_up:
            zones.append(
                ObZone(
                    market=previous.market,
                    timeframe=previous.timeframe,
                    lower=previous.low,
                    upper=previous.high,
                    created_at=current.candle_time,
                )
            )
    return zones


def detect_bullish_trap(
    candles: list[Candle], level: Decimal, reclaim_window: int
) -> TrapSignal | None:
    for index, item in enumerate(candles):
        if item.low < level and item.close < level:
            window = candles[index + 1 : index + 1 + reclaim_window]
            for reclaim in window:
                if reclaim.close > level:
                    return TrapSignal(
                        market=item.market,
                        timeframe=item.timeframe,
                        level=level,
                        swept_at=item.candle_time,
                        reclaimed_at=reclaim.candle_time,
                    )
    return None


def calculate_regression_channel(candles: list[Candle]) -> RegressionChannel:
    if not candles:
        return RegressionChannel(
            slope=Decimal("0"),
            center=[],
            upper=[],
            lower=[],
        )
    n = Decimal(len(candles))
    xs = [Decimal(index) for index in range(len(candles))]
    ys = [item.close for item in candles]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = (
        Decimal("0")
        if denominator == 0
        else sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    )
    intercept = mean_y - slope * mean_x
    center = [intercept + slope * x for x in xs]
    max_deviation = max(
        max(abs(item.high - fitted), abs(item.low - fitted))
        for item, fitted in zip(candles, center)
    )
    upper = [value + max_deviation for value in center]
    lower = [value - max_deviation for value in center]
    return RegressionChannel(slope=slope, center=center, upper=upper, lower=lower)


def find_confirmed_pivot_highs(
    candles: list[Candle], left: int, right: int
) -> list[PivotHigh]:
    pivots: list[PivotHigh] = []
    for index in range(left, len(candles) - right):
        candidate = candles[index]
        left_side = candles[index - left : index]
        right_side = candles[index + 1 : index + right + 1]
        if all(candidate.high > candle.high for candle in [*left_side, *right_side]):
            pivots.append(
                PivotHigh(
                    market=candidate.market,
                    timeframe=candidate.timeframe,
                    price=candidate.high,
                    pivot_time=candidate.candle_time,
                    confirmed_at=right_side[-1].candle_time,
                )
            )
    return pivots


def signal_from_pattern(
    market: str, pattern_score: int, hard_block_reasons: list[str]
) -> SignalDecision:
    hard_block_pass = not hard_block_reasons
    return SignalDecision(
        market=market,
        signal_score=pattern_score,
        hard_block_pass=hard_block_pass,
        can_create_trade_plan=hard_block_pass,
        reasons=hard_block_reasons,
    )


def _latest_positive_atr(candles: list[Candle]) -> Decimal:
    atr = calculate_atr(candles, period=14)
    latest = atr[-1] if atr else Decimal("0")
    return latest if latest > 0 else Decimal("1")


def _zones_overlap_enough(
    first_lower: Decimal,
    first_upper: Decimal,
    second_lower: Decimal,
    second_upper: Decimal,
) -> bool:
    overlap = min(first_upper, second_upper) - max(first_lower, second_lower)
    if overlap <= 0:
        return False
    smaller_width = min(first_upper - first_lower, second_upper - second_lower)
    if smaller_width <= 0:
        return False
    return overlap / smaller_width >= Decimal("0.3")


def _trend_filter_allows_long(candles: list[Candle]) -> bool:
    if len(candles) < 2:
        return True
    channel = calculate_regression_channel(candles)
    latest_close = candles[-1].close
    latest_center = channel.center[-1] if channel.center else latest_close
    if channel.slope < 0 and latest_close < latest_center:
        return False

    ema20 = calculate_ema(candles, period=20)
    ema60 = calculate_ema(candles, period=60)
    if ema20 and ema60 and ema20[-1] > ema60[-1]:
        return True
    return channel.slope > 0 or latest_close >= latest_center
