from decimal import Decimal

from fastapi.testclient import TestClient

from haley.api.server import create_app
from haley.audit_log import AuditLogger
from haley.api_contracts import StateChangeRequest
from haley.domain import (
    Alert,
    AlertSeverity,
    ExecutionEventType,
    OrderSide,
    OrderType,
    PositionState,
    RiskBlock,
    RiskBlockReason,
)
from haley.orders import OrderCoordinator
from haley.paper import PaperPortfolio
from haley.state_store import StateStore


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
    assert body["data"]["status"] == "running"


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
    assert body["data"]["top_alt_count"] == 12
    assert body["data"]["include_major_markets"] is True
    assert "live_trading_enabled" not in body["data"]


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
    assert body["data"]["status"] == "running"


def test_console_is_served_from_fastapi_app() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    response = client.get("/console")

    assert response.status_code == 200
    assert "Haley Operations Console" in response.text
    assert "/api/status" in response.text


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
