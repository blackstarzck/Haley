from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from haley.api_contracts import ApiResponse, StateChangeRequest
from haley.domain import (
    ModeState,
    OrderSide,
    OrderType,
    ReconciliationState,
    ReconciliationStatus,
    RuntimeMode,
    blocks_new_entry_statuses,
)
from haley.dry_run import DryRunOrderValidator
from haley.paper import PaperPortfolio
from haley.paper_runner import PaperRunner, PaperRunnerState
from haley.promotion import PromotionGateInput, evaluate_promotion_gate
from haley.recovery import RecoveryManager
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


def create_app(
    store: StateStore,
    runtime: ApiRuntimeState | None = None,
    ticker_client: Any | None = None,
    recovery_exchange: Any | None = None,
) -> FastAPI:
    app = FastAPI(title="Haley Operations API")
    state = runtime or ApiRuntimeState()
    state.mode = store.get_mode_state()
    paper_runner = PaperRunner(
        store=store,
        initial_cash_krw=state.paper_initial_cash_krw,
        top_alt_count=state.top_alt_count,
        include_major_markets=state.include_major_markets,
        mode=state.mode,
        ticker_client=ticker_client,
    )

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/console")

    @app.get("/favicon.ico", status_code=204)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/console")
    def console() -> FileResponse:
        path = Path(__file__).resolve().parents[3] / "web" / "operations-console.html"
        return FileResponse(path)

    @app.get("/api/status")
    def get_status(x_request_id: Annotated[str | None, Header()] = None) -> dict[str, Any]:
        request_id = x_request_id or "req_status"
        blocks = _unique_preserving_order(
            block.reason.value for block in store.list_risk_blocks()
        )
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
                    "unrealized_pnl": str(position.unrealized_pnl),
                    "stop_protected": position.stop_protected,
                    "stop_price": _decimal_text(position.stop_price),
                    "target1_price": _decimal_text(position.target1_price),
                    "target2_price": _decimal_text(position.target2_price),
                    "trailing_stop_price": _decimal_text(position.trailing_stop_price),
                    "management_stage": position.management_stage,
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
                    **_risk_block_guidance(block.reason.value),
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
                    "last_ticker_received_at": _datetime_text(
                        quality.last_ticker_received_at
                    ),
                    "last_trade_received_at": _datetime_text(
                        quality.last_trade_received_at
                    ),
                    "last_orderbook_received_at": _datetime_text(
                        quality.last_orderbook_received_at
                    ),
                    "last_candle_received_at": _datetime_text(
                        quality.last_candle_received_at
                    ),
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
        portfolio = _get_or_create_paper_portfolio(store, state.paper_initial_cash_krw)
        return ApiResponse.success(
            request_id=x_request_id or "req_settings",
            data={
                "mode": state.mode.mode.value,
                "paper_allow_real_order_api": state.mode.paper_allow_real_order_api,
                "live_trading_enabled": state.mode.live_trading_enabled,
                "paper_initial_cash_krw": _decimal_text(portfolio.initial_cash_krw),
                "paper_cash_krw": _decimal_text(portfolio.cash_krw),
                "paper_locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
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
        portfolio = _get_or_create_paper_portfolio(store, state.paper_initial_cash_krw)
        portfolio.initial_cash_krw = state.paper_initial_cash_krw
        store.save_paper_portfolio(portfolio)
        return ApiResponse.success(
            request_id=body.request_id,
            data={
                "paper_initial_cash_krw": _decimal_text(portfolio.initial_cash_krw),
                "paper_cash_krw": _decimal_text(portfolio.cash_krw),
                "paper_locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
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
        store.save_mode_state(state.mode)
        return ApiResponse.success(
            request_id=body.request_id,
            data={"kill_switch": {"enabled": True, "reason": body.reason}},
        )

    @app.post("/api/paper/reset")
    def reset_paper(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        portfolio = _get_or_create_paper_portfolio(store, state.paper_initial_cash_krw)
        portfolio.reset()
        store.save_paper_portfolio(portfolio)
        return ApiResponse.success(
            request_id=body.request_id,
            data={
                "cash_krw": _decimal_text(portfolio.cash_krw),
                "locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
            },
        )

    @app.post("/api/paper/experiment-reset")
    def reset_paper_experiment(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        portfolio = store.reset_paper_experiment_state(state.paper_initial_cash_krw)
        return ApiResponse.success(
            request_id=body.request_id,
            data={
                "cash_krw": _decimal_text(portfolio.cash_krw),
                "locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
                "cleared": [
                    "orders",
                    "fills",
                    "positions",
                    "stop_protections",
                    "risk_blocks",
                    "alerts",
                    "data_quality_states",
                    "reconciliation_state",
                ],
            },
        )

    @app.get("/api/paper/performance")
    def get_paper_performance(
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        report = store.get_latest_paper_performance_report()
        return ApiResponse.success(
            request_id=x_request_id or "req_paper_performance",
            data={} if report is None else _paper_performance_report_data(report),
        )

    @app.post("/api/recovery/run")
    def run_recovery(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        if recovery_exchange is None:
            recovery_run_id = f"recovery_{uuid4().hex}"
            run = {
                "recovery_run_id": recovery_run_id,
                "status": ReconciliationStatus.FAILED.value,
                "current_step": "exchange_not_configured",
                "operator_resume_required": False,
            }
            state.recovery_runs[recovery_run_id] = run
            store.save_reconciliation_state(
                ReconciliationState(status=ReconciliationStatus.FAILED)
            )
            return ApiResponse.success(
                request_id=body.request_id,
                data=run,
            )

        recovery_run = RecoveryManager(store=store, exchange=recovery_exchange).run()
        saved_state = store.get_reconciliation_state()
        run = {
            "recovery_run_id": recovery_run.recovery_run_id,
            "status": recovery_run.reconciliation_status.value,
            "current_step": None,
            "operator_resume_required": saved_state.operator_resume_required,
        }
        state.recovery_runs[recovery_run.recovery_run_id] = run
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
        validator = DryRunOrderValidator()
        result = validator.validate(
            market=body.market,
            side=body.side,
            order_type=body.order_type,
            quote_amount=None if body.quote_amount is None else Decimal(body.quote_amount),
            volume=None if body.volume is None else Decimal(body.volume),
            limit_price=None if body.limit_price is None else Decimal(body.limit_price),
        )
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
                "valid": result.valid,
                "reasons": result.reasons,
                "would_call_real_order_api": result.would_call_real_order_api,
                "request": details,
            },
        )

    @app.get("/api/promotion/status")
    def promotion_status(
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_promotion_status",
            data=_promotion_status_data(store),
        )

    @app.get("/api/paper-runner/status")
    def get_paper_runner_status(
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return ApiResponse.success(
            request_id=x_request_id or "req_paper_runner_status",
            data=_paper_runner_state_data(paper_runner.status()),
        )

    @app.post("/api/paper-runner/start")
    def start_paper_runner(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        return ApiResponse.success(
            request_id=body.request_id,
            data=_paper_runner_state_data(paper_runner.start()),
        )

    @app.post("/api/paper-runner/stop")
    def stop_paper_runner(body: StateChangeBody) -> dict[str, Any]:
        body.to_state_change()
        return ApiResponse.success(
            request_id=body.request_id,
            data=_paper_runner_state_data(paper_runner.stop()),
        )

    return app


def _decimal_text(value: Decimal | None) -> str:
    return "0" if value is None else str(value)


def _unique_preserving_order(values: Any) -> list[Any]:
    unique: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _datetime_text(value: Any | None) -> str | None:
    return None if value is None else value.isoformat()


def _risk_block_guidance(reason: str) -> dict[str, str]:
    guidance = {
        "UNPROTECTED_POSITION": {
            "explanation": "손절 감시가 없는 포지션이 있어 새 진입을 막았습니다.",
            "resolution": "포지션을 보호 상태로 만들거나 새 PAPER 실험을 시작하세요.",
            "next_action": "포지션과 손절가를 확인한 뒤 실험 리셋 또는 수동 정리를 선택하세요.",
        },
        "DATA_STALE": {
            "explanation": "시장 데이터가 오래되어 현재 가격 판단을 신뢰하기 어렵습니다.",
            "resolution": "데이터 수신이 재개될 때까지 기다리거나 수집기를 재시작하세요.",
            "next_action": "데이터 품질 화면에서 마지막 수신 시각을 확인하세요.",
        },
        "KILL_SWITCH_ON": {
            "explanation": "킬스위치가 켜져 있어 신규 주문을 막았습니다.",
            "resolution": "위험 원인을 확인한 뒤 별도 확인 절차로 해제하세요.",
            "next_action": "복구와 리스크 블록이 모두 해소되었는지 확인하세요.",
        },
    }
    return guidance.get(
        reason,
        {
            "explanation": "안전 조건이 충족되지 않아 신규 주문을 막았습니다.",
            "resolution": "관련 상태와 감사 로그를 확인하세요.",
            "next_action": "리스크 블록 상세를 검토하세요.",
        },
    )


def _get_or_create_paper_portfolio(
    store: StateStore,
    initial_cash_krw: Decimal,
) -> PaperPortfolio:
    try:
        return store.get_paper_portfolio()
    except KeyError:
        portfolio = PaperPortfolio(initial_cash_krw=initial_cash_krw)
        store.save_paper_portfolio(portfolio)
        return portfolio


def _paper_runner_state_data(state: PaperRunnerState) -> dict[str, Any]:
    return {
        "running": state.running,
        "mode": state.mode,
        "started_at": None if state.started_at is None else state.started_at.isoformat(),
        "stopped_at": None if state.stopped_at is None else state.stopped_at.isoformat(),
        "last_tick_at": None if state.last_tick_at is None else state.last_tick_at.isoformat(),
        "selected_markets": state.selected_markets,
        "last_action": state.last_action,
        "last_block_reason": state.last_block_reason,
        "last_signal": state.last_signal,
        "last_trade_plan": state.last_trade_plan,
        "paper_cash_krw": state.paper_cash_krw,
        "paper_locked_cash_krw": state.paper_locked_cash_krw,
    }


def _paper_performance_report_data(report: Any) -> dict[str, Any]:
    return {
        "session_id": report.session_id,
        "realized_pnl_krw": str(report.realized_pnl_krw),
        "fee_krw": str(report.fee_krw),
        "net_pnl_krw": str(report.net_pnl_krw),
        "trade_count": report.trade_count,
        "win_count": report.win_count,
        "loss_count": report.loss_count,
        "win_rate": str(report.win_rate),
        "max_drawdown_krw": str(report.max_drawdown_krw),
        "average_r": str(report.average_r),
        "mae_krw": str(report.mae_krw),
        "mfe_krw": str(report.mfe_krw),
        "signal_count": report.signal_count,
        "blocked_count": report.blocked_count,
    }


def _promotion_status_data(store: StateStore) -> dict[str, Any]:
    blocking_statuses = blocks_new_entry_statuses()
    unknown_order_count = sum(
        1 for order in store.list_orders() if order.status in blocking_statuses
    )
    gate_input = PromotionGateInput(
        paper_runtime_days=0,
        paper_signal_count=0,
        dry_run_passed=False,
        real_order_api_call_count=0,
        unresolved_risk_block_count=len(store.list_risk_blocks()),
        unknown_order_count=unknown_order_count,
    )
    result = evaluate_promotion_gate(gate_input)
    return {
        "allowed": result.allowed,
        "unmet_conditions": result.unmet_conditions,
        "paper_runtime_days": gate_input.paper_runtime_days,
        "paper_signal_count": gate_input.paper_signal_count,
        "dry_run_passed": gate_input.dry_run_passed,
        "real_order_api_call_count": gate_input.real_order_api_call_count,
        "unresolved_risk_block_count": gate_input.unresolved_risk_block_count,
        "unknown_order_count": gate_input.unknown_order_count,
    }
