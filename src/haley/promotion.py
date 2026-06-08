from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionGateInput:
    paper_runtime_days: int
    paper_signal_count: int
    dry_run_passed: bool
    real_order_api_call_count: int
    unresolved_risk_block_count: int
    unknown_order_count: int


@dataclass(frozen=True)
class PromotionGateResult:
    allowed: bool
    unmet_conditions: list[str]


def evaluate_promotion_gate(data: PromotionGateInput) -> PromotionGateResult:
    unmet: list[str] = []
    if data.paper_runtime_days < 28:
        unmet.append("PAPER_RUNTIME_DAYS_LT_28")
    if data.paper_signal_count < 200:
        unmet.append("PAPER_SIGNAL_COUNT_LT_200")
    if not data.dry_run_passed:
        unmet.append("DRY_RUN_NOT_PASSED")
    if data.real_order_api_call_count != 0:
        unmet.append("REAL_ORDER_API_CALL_COUNT_NOT_ZERO")
    if data.unresolved_risk_block_count > 0:
        unmet.append("UNRESOLVED_RISK_BLOCKS")
    if data.unknown_order_count > 0:
        unmet.append("UNKNOWN_ORDERS_EXIST")
    return PromotionGateResult(allowed=not unmet, unmet_conditions=unmet)
