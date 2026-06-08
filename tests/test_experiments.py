from decimal import Decimal

from haley.experiments import (
    ExperimentSession,
    PaperPerformanceReport,
    SignalJournalEntry,
    build_paper_performance_report,
)
from haley.state_store import StateStore


def test_experiment_session_can_be_saved_and_listed() -> None:
    store = StateStore.in_memory()
    session = ExperimentSession.start(
        strategy_version="UFS-R1.0",
        initial_cash_krw=Decimal("1000000"),
        markets=["KRW-XRP", "KRW-WLD"],
    )

    store.create_experiment_session(session)
    sessions = store.list_experiment_sessions()

    assert sessions[0].session_id == session.session_id
    assert sessions[0].strategy_version == "UFS-R1.0"
    assert sessions[0].markets == ["KRW-XRP", "KRW-WLD"]


def test_signal_journal_entry_records_signal_and_outcome_fields() -> None:
    store = StateStore.in_memory()
    entry = SignalJournalEntry(
        entry_id="journal-1",
        session_id="session-1",
        market="KRW-XRP",
        strategy="UFS-R1",
        signal_score=90,
        reasons=["BULLISH_FVG", "BULLISH_OB", "BULLISH_TRAP"],
        rejected_reasons=[],
        entry_price=Decimal("500"),
        stop_price=Decimal("450"),
        target1_price=Decimal("550"),
        target2_price=Decimal("600"),
    )

    store.save_signal_journal_entry(entry)
    saved = store.list_signal_journal_entries("session-1")

    assert saved[0].market == "KRW-XRP"
    assert saved[0].signal_score == 90
    assert saved[0].reasons == ["BULLISH_FVG", "BULLISH_OB", "BULLISH_TRAP"]


def test_paper_performance_report_summarizes_session_results() -> None:
    report = build_paper_performance_report(
        session_id="session-1",
        realized_pnl_krw=Decimal("12000"),
        fee_krw=Decimal("500"),
        trade_count=10,
        win_count=6,
        loss_count=4,
        max_drawdown_krw=Decimal("3000"),
        average_r=Decimal("0.45"),
        mae_krw=Decimal("2500"),
        mfe_krw=Decimal("7000"),
        signal_count=30,
        blocked_count=3,
    )

    assert isinstance(report, PaperPerformanceReport)
    assert report.session_id == "session-1"
    assert report.net_pnl_krw == Decimal("11500")
    assert report.win_rate == Decimal("0.6")
    assert report.signal_count == 30
    assert report.blocked_count == 3


def test_paper_performance_report_can_be_saved_and_loaded() -> None:
    store = StateStore.in_memory()
    report = build_paper_performance_report(
        session_id="session-1",
        realized_pnl_krw=Decimal("12000"),
        fee_krw=Decimal("500"),
        trade_count=10,
        win_count=6,
        loss_count=4,
        max_drawdown_krw=Decimal("3000"),
        average_r=Decimal("0.45"),
        mae_krw=Decimal("2500"),
        mfe_krw=Decimal("7000"),
        signal_count=30,
        blocked_count=3,
    )

    store.save_paper_performance_report(report)
    saved = store.get_latest_paper_performance_report()

    assert saved is not None
    assert saved.session_id == "session-1"
    assert saved.net_pnl_krw == Decimal("11500")
