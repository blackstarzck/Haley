from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True)
class ExperimentSession:
    session_id: str
    strategy_version: str
    initial_cash_krw: Decimal
    markets: list[str]
    started_at: datetime
    stopped_at: datetime | None = None

    @classmethod
    def start(
        cls,
        strategy_version: str,
        initial_cash_krw: Decimal,
        markets: list[str],
    ) -> ExperimentSession:
        return cls(
            session_id=f"paper_session_{uuid4().hex}",
            strategy_version=strategy_version,
            initial_cash_krw=initial_cash_krw,
            markets=list(markets),
            started_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class SignalJournalEntry:
    entry_id: str
    session_id: str
    market: str
    strategy: str
    signal_score: int
    reasons: list[str]
    rejected_reasons: list[str]
    entry_price: Decimal | None
    stop_price: Decimal | None
    target1_price: Decimal | None
    target2_price: Decimal | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class PaperPerformanceReport:
    session_id: str
    realized_pnl_krw: Decimal
    fee_krw: Decimal
    net_pnl_krw: Decimal
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: Decimal
    max_drawdown_krw: Decimal
    average_r: Decimal
    mae_krw: Decimal
    mfe_krw: Decimal
    signal_count: int
    blocked_count: int


def build_paper_performance_report(
    *,
    session_id: str,
    realized_pnl_krw: Decimal,
    fee_krw: Decimal,
    trade_count: int,
    win_count: int,
    loss_count: int,
    max_drawdown_krw: Decimal,
    average_r: Decimal,
    mae_krw: Decimal,
    mfe_krw: Decimal,
    signal_count: int,
    blocked_count: int,
) -> PaperPerformanceReport:
    win_rate = Decimal("0") if trade_count == 0 else Decimal(win_count) / Decimal(trade_count)
    return PaperPerformanceReport(
        session_id=session_id,
        realized_pnl_krw=realized_pnl_krw,
        fee_krw=fee_krw,
        net_pnl_krw=realized_pnl_krw - fee_krw,
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
        max_drawdown_krw=max_drawdown_krw,
        average_r=average_r,
        mae_krw=mae_krw,
        mfe_krw=mfe_krw,
        signal_count=signal_count,
        blocked_count=blocked_count,
    )
