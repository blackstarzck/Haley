from haley.promotion import PromotionGateInput, evaluate_promotion_gate


def test_promotion_gate_lists_unmet_conditions() -> None:
    result = evaluate_promotion_gate(
        PromotionGateInput(
            paper_runtime_days=3,
            paper_signal_count=12,
            dry_run_passed=False,
            real_order_api_call_count=0,
            unresolved_risk_block_count=1,
            unknown_order_count=0,
        )
    )

    assert result.allowed is False
    assert result.unmet_conditions == [
        "PAPER_RUNTIME_DAYS_LT_28",
        "PAPER_SIGNAL_COUNT_LT_200",
        "DRY_RUN_NOT_PASSED",
        "UNRESOLVED_RISK_BLOCKS",
    ]
