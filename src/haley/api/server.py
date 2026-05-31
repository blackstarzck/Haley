from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from haley.api_contracts import ApiResponse, StateChangeRequest
from haley.domain import ModeState, OrderSide, OrderType, RuntimeMode
from haley.paper import PaperPortfolio
from haley.state_store import StateStore


@dataclass
class ApiRuntimeState:
    mode: ModeState = field(default_factory=ModeState)
    paper_initial_cash_krw: Decimal = Decimal("1000000")
    top_alt_count: int = 10
    include_major_markets: bool = False
    recovery_runs: dict[str, dict[str, Any]] = field(default_factory=dict)


class StateChangeBody(BaseModel):
    request_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    def to_state_change(self) -> StateChangeRequest:
        return StateChangeRequest(
            request_id=self.request_id,
            idempotency_key=self.idempotency_key,
            operator_id=self.operator_id,
            reason=self.reason,
        )


class PaperSettingsBody(StateChangeBody):
    paper_initial_cash_krw: str = Field(min_length=1)
    top_alt_count: int = Field(ge=1, le=100)
    include_major_markets: bool


class DryRunOrderBody(BaseModel):
    market: str = Field(pattern=r"^KRW-[A-Z0-9]+$")
    side: OrderSide
    order_type: OrderType
    quote_amount: str | None = None
    volume: str | None = None
    limit_price: str | None = None


def create_app(store: StateStore, runtime: ApiRuntimeState | None = None) -> FastAPI:
    app = FastAPI(title="Haley Operations API")
    state = runtime or ApiRuntimeState()

    @app.get("/console")
    def console() -> FileResponse:
        path = Path(__file__).resolve().parents[3] / "web" / "operations-console.html"
        return FileResponse(path)

    @app.get("/api/status")
    def get_status(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        request_id = x_request_id or "req_status"
        blocks = [block.reason.value for block in store.list_risk_blocks()]
        return ApiResponse.success(
            request_id=request_id,
            data={
                "mode": state.mode.mode.value,
                "can_place_new_order": not blocks
                and not state.mode.kill_switch_enabled
                and state.mode.mode is RuntimeMode.PAPER,
                "global_blocks": blocks,
                "kill_switch": {
                    "enabled": state.mode.kill_switch_enabled,
                    "reason": None,
                },
                "recovery_state": {
                    "status": store.get_reconciliation_state().status.value,
                    "current_step": None,
                },
            },
        )

    @app.get("/api/orders")
    def list_orders(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_orders",
            data=[
                {
                    "order_id": order.order_id,
                    "market": order.intent.market,
                    "client_order_key": order.intent.client_order_key,
                    "exchange_identifier": order.intent.exchange_identifier,
                    "status": order.status.value,
                    "side": order.intent.side.value,
                    "order_type": order.intent.order_type.value,
                    "quote_amount": _decimal_text(order.intent.quote_amount),
                    "volume": _decimal_text(order.intent.volume),
                    "limit_price": _decimal_text(order.intent.limit_price),
                    "updated_at": order.updated_at.isoformat(),
                }
                for order in store.list_orders()
            ],
        )

    @app.get("/api/positions")
    def list_positions(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_positions",
            data=[
                {
                    "market": position.market,
                    "volume": str(position.volume),
                    "average_entry_price": str(position.average_entry_price),
                    "realized_pnl": str(position.realized_pnl),
                    "stop_protected": position.stop_protected,
                    "updated_at": position.updated_at.isoformat(),
                }
                for position in store.list_positions()
            ],
        )

    @app.get("/api/risk/blocks")
    def list_risk_blocks(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_risk_blocks",
            data=[
                {
                    "reason": block.reason.value,
                    "market": block.market,
                    "detail": block.detail,
                    "created_at": block.created_at.isoformat(),
                }
                for block in store.list_risk_blocks()
            ],
        )

    @app.get("/api/data-quality")
    def list_data_quality(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_data_quality",
            data={
                market: {
                    "stale": quality.stale,
                    "rest_ws_mismatch": quality.rest_ws_mismatch,
                    "market_warning": quality.market_warning,
                    "orderbook_gap": quality.orderbook_gap,
                    "allows_new_entry": quality.allows_new_entry,
                }
                for market, quality in store.list_data_quality_states().items()
            },
        )

    @app.get("/api/alerts")
    def list_alerts(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_alerts",
            data=[
                {
                    "alert_id": alert.alert_id,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "created_at": alert.created_at.isoformat(),
                    "acknowledged_at": None
                    if alert.acknowledged_at is None
                    else alert.acknowledged_at.isoformat(),
                }
                for alert in store.list_alerts()
            ],
        )

    @app.post("/api/alerts/{alert_id}/ack")
    def ack_alert(alert_id: str, body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        store.ack_alert(alert_id)
        return ApiResponse.success(
            request_id=body.request_id,
            data={"alert_id": alert_id, "acknowledged": True},
        )

    @app.get("/api/audit-events")
    def list_audit_events(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_audit_events",
            data=[
                {
                    "event_id": event.event_id,
                    "order_id": event.order_id,
                    "event_type": event.event_type.value,
                    "occurred_at": event.occurred_at.isoformat(),
                    "payload": dict(event.payload),
                    "operator_id": event.operator_id,
                    "reason": event.reason,
                }
                for event in store.list_execution_events()
            ],
        )

    @app.get("/api/settings")
    def get_settings(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_settings",
            data={
                "mode": state.mode.mode.value,
                "paper_allow_real_order_api": state.mode.paper_allow_real_order_api,
                "live_trading_enabled": state.mode.live_trading_enabled,
                "paper_initial_cash_krw": str(state.paper_initial_cash_krw),
                "top_alt_count": state.top_alt_count,
                "include_major_markets": state.include_major_markets,
            },
        )

    @app.patch("/api/settings/paper")
    def patch_paper_settings(body: PaperSettingsBody) -> dict[str, Any]:
        body.to_state_change()
        state.paper_initial_cash_krw = Decimal(body.paper_initial_cash_krw)
        state.top_alt_count = body.top_alt_count
        state.include_major_markets = body.include_major_markets
        return ApiResponse.success(
            request_id=body.request_id,
            data={
                "paper_initial_cash_krw": str(state.paper_initial_cash_krw),
                "top_alt_count": state.top_alt_count,
                "include_major_markets": state.include_major_markets,
            },
        )

    @app.post("/api/kill-switch/enable")
    def enable_kill_switch(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        state.mode = ModeState(
            mode=RuntimeMode.KILL_SWITCHED,
            live_trading_enabled=False,
            paper_allow_real_order_api=False,
            kill_switch_enabled=True,
        )
        return ApiResponse.success(
            request_id=body.request_id,
            data={"kill_switch": {"enabled": True, "reason": body.reason}},
        )

    @app.post("/api/paper/reset")
    def reset_paper(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        portfolio = store.get_paper_portfolio()
        portfolio.reset()
        store.save_paper_portfolio(portfolio)
        return ApiResponse.success(
            request_id=body.request_id,
            data={
                "cash_krw": _decimal_text(portfolio.cash_krw),
                "locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
            },
        )

    @app.post("/api/recovery/run")
    def run_recovery(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        recovery_run_id = f"recovery_{uuid4().hex}"
        run = {
            "recovery_run_id": recovery_run_id,
            "status": "running",
            "current_step": "balance_lookup",
        }
        state.recovery_runs[recovery_run_id] = run
        return ApiResponse.success(
            request_id=body.request_id,
            data=run,
        )

    @app.get("/api/recovery/runs/{recovery_run_id}")
    def get_recovery_run(
        recovery_run_id: str,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_recovery_run",
            data=state.recovery_runs[recovery_run_id],
        )

    @app.post("/api/dry-run/order")
    def dry_run_order(body: DryRunOrderBody) -> dict[str, Any]:
        details = {
            "market": body.market,
            "side": body.side.value,
            "order_type": body.order_type.value,
            "quote_amount": body.quote_amount,
            "volume": body.volume,
            "limit_price": body.limit_price,
        }
        return ApiResponse.success(
            request_id="req_dry_run_order",
            data={
                "valid": True,
                "would_call_real_order_api": False,
                "request": details,
            },
        )

    return app


def _decimal_text(value: Decimal | None) -> str:
    return "0" if value is None else str(value)
