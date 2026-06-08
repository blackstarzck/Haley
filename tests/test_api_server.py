from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from haley.api.server import create_app
from haley.audit_log import AuditLogger
from haley.api_contracts import StateChangeRequest
from haley.experiments import build_paper_performance_report
from haley.domain import (
    Alert,
    AlertSeverity,
    DataQualityState,
    ExecutionEventType,
    OrderSide,
    OrderType,
    PositionState,
    ReconciliationStatus,
    RiskBlock,
    RiskBlockReason,
    RuntimeMode,
)
from haley.orders import OrderCoordinator
from haley.paper import PaperPortfolio
from haley.state_store import StateStore


class FakeTickerClient:
    def list_all_tickers(self, quote_currencies: list[str]) -> list[dict[str, object]]:
        assert quote_currencies == ["KRW"]
        return [
            {"market": "KRW-XRP", "acc_trade_price_24h": "1000", "trade_price": "500"},
        ]


class FakeRecoveryExchange:
    def list_accounts(self) -> list[dict[str, object]]:
        return []

    def list_open_orders(self) -> list[dict[str, object]]:
        return []


def test_status_api_returns_common_response_shape() -> None:
    store = StateStore.in_memory()
    app = create_app(store=store)
    client = TestClient(app)

    response = client.get("/api/status", headers={"X-Request-ID": "req-1"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-1"
    assert "server_time" in body
    assert body["data"]["mode"] == "PAPER"
    assert body["data"]["can_place_new_order"] is True


def test_status_api_deduplicates_global_blocks_for_summary() -> None:
    store = StateStore.in_memory()
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.UNPROTECTED_POSITION,
            market="KRW-XRP",
            detail="first",
        )
    )
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.UNPROTECTED_POSITION,
            market="KRW-XRP",
            detail="second",
        )
    )
    client = TestClient(create_app(store=store))

    body = client.get("/api/status").json()

    assert body["data"]["can_place_new_order"] is False
    assert body["data"]["global_blocks"] == ["UNPROTECTED_POSITION"]


def test_positions_api_returns_decimal_values_as_strings() -> None:
    store = StateStore.in_memory()
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10.5"),
            average_entry_price=Decimal("500.1"),
            realized_pnl=Decimal("120.25"),
        )
    )
    client = TestClient(create_app(store=store))

    body = client.get("/api/positions").json()

    assert body["data"][0]["volume"] == "10.5"
    assert body["data"][0]["average_entry_price"] == "500.1"
    assert body["data"][0]["realized_pnl"] == "120.25"


def test_risk_blocks_alerts_and_data_quality_apis() -> None:
    store = StateStore.in_memory()
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.DATA_STALE,
            market="KRW-XRP",
            detail="stale",
        )
    )
    store.create_alert(
        Alert(
            alert_id="alert-1",
            severity=AlertSeverity.CRITICAL,
            message="DATA_STALE",
        )
    )
    client = TestClient(create_app(store=store))

    risk_body = client.get("/api/risk/blocks").json()
    alert_body = client.get("/api/alerts").json()
    data_quality_body = client.get("/api/data-quality").json()

    assert risk_body["data"][0]["reason"] == "DATA_STALE"
    assert alert_body["data"][0]["alert_id"] == "alert-1"
    assert data_quality_body["data"] == {}


def test_risk_blocks_api_returns_user_guidance() -> None:
    store = StateStore.in_memory()
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.UNPROTECTED_POSITION,
            market="KRW-XRP",
            detail="An open position has no stop protection.",
        )
    )
    client = TestClient(create_app(store=store))

    item = client.get("/api/risk/blocks").json()["data"][0]

    assert item["explanation"]
    assert item["resolution"]
    assert item["next_action"]


def test_data_quality_api_returns_feed_specific_timestamps() -> None:
    store = StateStore.in_memory()
    observed_at = datetime(2026, 5, 31, 0, 0, tzinfo=UTC)
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(
            stale=False,
            rest_ws_mismatch=False,
            last_ticker_received_at=observed_at,
            last_trade_received_at=observed_at,
            last_orderbook_received_at=observed_at,
            last_candle_received_at=observed_at,
        ),
    )
    client = TestClient(create_app(store=store))

    body = client.get("/api/data-quality").json()

    assert body["data"]["KRW-XRP"]["last_ticker_received_at"] == observed_at.isoformat()
    assert body["data"]["KRW-XRP"]["last_trade_received_at"] == observed_at.isoformat()
    assert body["data"]["KRW-XRP"]["last_orderbook_received_at"] == observed_at.isoformat()
    assert body["data"]["KRW-XRP"]["last_candle_received_at"] == observed_at.isoformat()


def test_kill_switch_enable_requires_state_change_request() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    bad = client.post("/api/kill-switch/enable", json={})
    good = client.post(
        "/api/kill-switch/enable",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "manual stop",
        },
    )

    assert bad.status_code == 422
    assert good.status_code == 200
    assert good.json()["data"]["kill_switch"]["enabled"] is True


def test_kill_switch_enable_persists_mode_state() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    response = client.post(
        "/api/kill-switch/enable",
        json={
            "request_id": "req-kill",
            "idempotency_key": "idem-kill",
            "operator_id": "local-user",
            "reason": "manual stop",
        },
    )

    assert response.status_code == 200
    saved = store.get_mode_state()
    assert saved.mode is RuntimeMode.KILL_SWITCHED
    assert saved.kill_switch_enabled is True


def test_paper_reset_api_resets_virtual_cash() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(
        PaperPortfolio(
            initial_cash_krw=Decimal("1000000"),
            cash_krw=Decimal("900000"),
            locked_cash_krw=Decimal("50000"),
        )
    )
    client = TestClient(create_app(store=store))

    body = client.post(
        "/api/paper/reset",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "paper reset",
        },
    ).json()

    assert body["data"]["cash_krw"] == "1000000"
    assert body["data"]["locked_cash_krw"] == "0"


def test_paper_experiment_reset_clears_virtual_trading_state() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
        )
    )
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.UNPROTECTED_POSITION,
            market="KRW-XRP",
            detail="unprotected",
        )
    )
    client = TestClient(create_app(store=store))

    response = client.post(
        "/api/paper/experiment-reset",
        json={
            "request_id": "req-reset",
            "idempotency_key": "idem-reset",
            "operator_id": "local-user",
            "reason": "start new paper experiment",
        },
    )

    assert response.status_code == 200
    assert store.list_positions() == []
    assert store.list_orders() == []
    assert store.list_risk_blocks() == []


def test_paper_performance_api_returns_latest_report() -> None:
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
    client = TestClient(create_app(store=store))

    body = client.get("/api/paper/performance").json()

    assert body["data"]["session_id"] == "session-1"
    assert body["data"]["realized_pnl_krw"] == "12000"
    assert body["data"]["fee_krw"] == "500"
    assert body["data"]["net_pnl_krw"] == "11500"
    assert body["data"]["trade_count"] == 10
    assert body["data"]["win_rate"] == "0.6"
    assert body["data"]["max_drawdown_krw"] == "3000"
    assert body["data"]["average_r"] == "0.45"
    assert body["data"]["mae_krw"] == "2500"
    assert body["data"]["mfe_krw"] == "7000"
    assert body["data"]["signal_count"] == 30
    assert body["data"]["blocked_count"] == 3


def test_orders_api_returns_order_contract_without_sensitive_values() -> None:
    store = StateStore.in_memory()
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("50000"),
        volume=Decimal("100"),
        limit_price=Decimal("500"),
        exchange_identifier="upbit-id",
        state_change=StateChangeRequest(
            request_id="req-1",
            idempotency_key="idem-1",
            operator_id="local-user",
            reason="paper order",
        ),
    )
    client = TestClient(create_app(store=store))

    body = client.get("/api/orders").json()

    assert body["data"][0]["order_id"] == order.order_id
    assert body["data"][0]["quote_amount"] == "50000"
    assert "secret" not in str(body).lower()


def test_alert_ack_api_updates_acknowledged_at() -> None:
    store = StateStore.in_memory()
    store.create_alert(
        Alert(
            alert_id="alert-1",
            severity=AlertSeverity.WARNING,
            message="check",
        )
    )
    client = TestClient(create_app(store=store))

    response = client.post(
        "/api/alerts/alert-1/ack",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "checked",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["alert_id"] == "alert-1"
    assert store.list_alerts()[0].acknowledged_at is not None


def test_recovery_run_api_returns_recovery_run_id() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    body = client.post(
        "/api/recovery/run",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "startup recovery",
        },
    ).json()

    assert body["data"]["recovery_run_id"].startswith("recovery_")
    assert body["data"]["status"] == "FAILED"


def test_recovery_run_api_updates_reconciliation_state_without_auto_resume() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store, recovery_exchange=FakeRecoveryExchange()))

    body = client.post(
        "/api/recovery/run",
        json={
            "request_id": "req-recovery",
            "idempotency_key": "idem-recovery",
            "operator_id": "local-user",
            "reason": "startup recovery",
        },
    ).json()

    assert body["data"]["status"] == "MATCHED"
    assert store.get_reconciliation_state().status is ReconciliationStatus.MATCHED
    assert store.get_reconciliation_state().allows_new_entry is False
    assert body["data"]["operator_resume_required"] is True


def test_audit_events_api_returns_masked_payload() -> None:
    store = StateStore.in_memory()
    AuditLogger(store).log(
        event_type=ExecutionEventType.ORDER_TRANSITION,
        payload={"secret_key": "hidden", "safe": "value"},
    )
    client = TestClient(create_app(store=store))

    body = client.get("/api/audit-events").json()

    assert body["data"][0]["payload"]["secret_key"] == "[REDACTED]"
    assert body["data"][0]["payload"]["safe"] == "value"


def test_patch_paper_settings_updates_safe_paper_values_only() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(
        PaperPortfolio(
            initial_cash_krw=Decimal("1000000"),
            cash_krw=Decimal("900000"),
            locked_cash_krw=Decimal("50000"),
        )
    )
    client = TestClient(create_app(store=store))

    body = client.patch(
        "/api/settings/paper",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "paper settings",
            "paper_initial_cash_krw": "2000000",
            "top_alt_count": 12,
            "include_major_markets": True,
        },
    ).json()

    assert body["data"]["paper_initial_cash_krw"] == "2000000"
    assert body["data"]["paper_cash_krw"] == "900000"
    assert body["data"]["paper_locked_cash_krw"] == "50000"
    assert body["data"]["top_alt_count"] == 12
    assert body["data"]["include_major_markets"] is True
    assert "live_trading_enabled" not in body["data"]

    saved = store.get_paper_portfolio()
    assert saved.initial_cash_krw == Decimal("2000000")
    assert saved.cash_krw == Decimal("900000")
    assert saved.locked_cash_krw == Decimal("50000")


def test_dry_run_order_validates_request_without_creating_order() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    body = client.post(
        "/api/dry-run/order",
        json={
            "market": "KRW-XRP",
            "side": "bid",
            "order_type": "limit",
            "quote_amount": "5000",
            "volume": "10",
            "limit_price": "500",
        },
    ).json()

    assert body["data"]["valid"] is True
    assert body["data"]["would_call_real_order_api"] is False
    assert store.list_orders() == []


def test_dry_run_order_rejects_below_minimum_without_creating_order() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    body = client.post(
        "/api/dry-run/order",
        json={
            "market": "KRW-XRP",
            "side": "bid",
            "order_type": "limit",
            "quote_amount": "4999",
            "volume": "10",
            "limit_price": "500",
        },
    ).json()

    assert body["data"]["valid"] is False
    assert body["data"]["reasons"] == ["MIN_QUOTE_AMOUNT"]
    assert body["data"]["would_call_real_order_api"] is False
    assert store.list_orders() == []


def test_live_trading_remains_locked_in_first_release() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    settings = client.get("/api/settings").json()["data"]

    assert settings["live_trading_enabled"] is False
    assert settings["paper_allow_real_order_api"] is False


def test_promotion_status_api_returns_unmet_conditions() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    body = client.get("/api/promotion/status").json()

    assert body["data"]["allowed"] is False
    assert "PAPER_RUNTIME_DAYS_LT_28" in body["data"]["unmet_conditions"]
    assert "PAPER_SIGNAL_COUNT_LT_200" in body["data"]["unmet_conditions"]
    assert "DRY_RUN_NOT_PASSED" in body["data"]["unmet_conditions"]


def test_paper_runner_apis_start_stop_and_report_status() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    client = TestClient(create_app(store=store))

    initial = client.get("/api/paper-runner/status").json()
    bad_start = client.post("/api/paper-runner/start", json={})
    started = client.post(
        "/api/paper-runner/start",
        json={
            "request_id": "req-runner-start",
            "idempotency_key": "idem-runner-start",
            "operator_id": "local-user",
            "reason": "start paper runner",
        },
    ).json()
    stopped = client.post(
        "/api/paper-runner/stop",
        json={
            "request_id": "req-runner-stop",
            "idempotency_key": "idem-runner-stop",
            "operator_id": "local-user",
            "reason": "stop paper runner",
        },
    ).json()

    assert initial["data"]["running"] is False
    assert bad_start.status_code == 422
    assert started["request_id"] == "req-runner-start"
    assert started["data"]["running"] is True
    assert started["data"]["mode"] == "PAPER"
    assert started["data"]["paper_cash_krw"] == "1000000"
    assert stopped["request_id"] == "req-runner-stop"
    assert stopped["data"]["running"] is False


def test_paper_runner_api_uses_injected_public_ticker_client() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    client = TestClient(create_app(store=store, ticker_client=FakeTickerClient()))

    client.post(
        "/api/paper-runner/start",
        json={
            "request_id": "req-runner-start",
            "idempotency_key": "idem-runner-start",
            "operator_id": "local-user",
            "reason": "start paper runner",
        },
    )
    body = client.get("/api/paper-runner/status").json()

    client.post(
        "/api/paper-runner/stop",
        json={
            "request_id": "req-runner-stop",
            "idempotency_key": "idem-runner-stop",
            "operator_id": "local-user",
            "reason": "stop paper runner",
        },
    )

    assert body["data"]["selected_markets"] == ["KRW-XRP"]
    assert body["data"]["last_tick_at"] is not None
    assert body["data"]["last_action"] == "NO_SIGNAL"
    assert body["data"]["last_block_reason"] == "NO_SIGNAL"


def test_get_recovery_run_returns_run_status() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))
    created = client.post(
        "/api/recovery/run",
        json={
            "request_id": "req-1",
            "idempotency_key": "idem-1",
            "operator_id": "local-user",
            "reason": "startup recovery",
        },
    ).json()
    recovery_run_id = created["data"]["recovery_run_id"]

    body = client.get(f"/api/recovery/runs/{recovery_run_id}").json()

    assert body["data"]["recovery_run_id"] == recovery_run_id
    assert body["data"]["status"] == "FAILED"


def test_console_is_served_from_fastapi_app() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    response = client.get("/console")

    assert response.status_code == 200
    assert "Haley Operations Console" in response.text
    assert "/api/status" in response.text
    assert "/api/paper-runner/status" in response.text
    assert "/api/data-quality" in response.text
    assert "paperInitialCash" in response.text
    assert "lastTickValue" in response.text
    assert "lastSignalValue" in response.text
    assert "dataQualityBody" in response.text
    assert "stop_price" in response.text


def test_root_redirects_to_console() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store), follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/console"


def test_favicon_request_returns_empty_response() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    response = client.get("/favicon.ico")

    assert response.status_code == 204
