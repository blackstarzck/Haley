from pathlib import Path


CONSOLE_HTML = Path("web") / "operations-console.html"


def test_operations_console_reference_dashboard_structure() -> None:
    html = CONSOLE_HTML.read_text(encoding="utf-8")

    required_text = [
        "Obsidian Signal",
        "UFS-R1 Strategy",
        "Total Equity",
        "Portfolio Summary",
        "SYSTEM STATUS",
        "RISK METRICS",
        "OPEN POSITIONS",
        "SETUP WATCHLIST",
        "AUDIT LOG",
        "Kill Switch",
    ]
    for text in required_text:
        assert text in html

    required_ids = [
        'id="modePaper"',
        'id="modeLive"',
        'id="totalEquityValue"',
        'id="safetyPriorityRail"',
        'id="auditEventsBody"',
        'id="ordersBody"',
        'id="positionsBody"',
        'id="riskBody"',
        'id="dataQualityBody"',
    ]
    for marker in required_ids:
        assert marker in html

    required_api_paths = [
        '"/api/status"',
        '"/api/orders"',
        '"/api/positions"',
        '"/api/risk/blocks"',
        '"/api/alerts"',
        '"/api/audit-events"',
        '"/api/settings"',
        '"/api/paper-runner/status"',
        '"/api/data-quality"',
        '"/api/promotion/status"',
    ]
    for path in required_api_paths:
        assert path in html


def test_console_contains_promotion_gate_unmet_conditions() -> None:
    html = CONSOLE_HTML.read_text(encoding="utf-8")

    assert "promotionStatus" in html
    assert "LIVE 전환 조건 미충족" in html
    assert "PAPER_RUNTIME_DAYS_LT_28" in html
    assert "PAPER_SIGNAL_COUNT_LT_200" in html
    assert "DRY_RUN_NOT_PASSED" in html


def test_console_contains_user_guidance_and_confirmations() -> None:
    html = CONSOLE_HTML.read_text(encoding="utf-8")

    assert "confirmAction" in html
    assert "explanation" in html
    assert "resolution" in html
    assert "next_action" in html
    assert "LIVE 전환 조건" in html
