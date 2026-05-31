from datetime import UTC, datetime

import pytest

from haley.api_contracts import (
    ApiError,
    ApiResponse,
    StateChangeRequest,
    utc_isoformat,
)


def test_success_response_includes_server_time_request_id_and_data() -> None:
    response = ApiResponse.success(
        data={"mode": "PAPER"},
        request_id="req-1",
        server_time=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
    )

    assert response == {
        "server_time": "2026-05-31T00:00:00Z",
        "request_id": "req-1",
        "data": {"mode": "PAPER"},
    }


def test_error_response_uses_common_shape() -> None:
    response = ApiResponse.error(
        request_id="req-1",
        error=ApiError(
            code="UNKNOWN_ORDER_EXISTS",
            message="같은 마켓에 상태 미확정 주문이 있어 신규 주문을 만들 수 없습니다.",
            retryable=False,
            details={"market": "KRW-XRP"},
        ),
        server_time=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
    )

    assert response == {
        "server_time": "2026-05-31T00:00:00Z",
        "request_id": "req-1",
        "error": {
            "code": "UNKNOWN_ORDER_EXISTS",
            "message": "같은 마켓에 상태 미확정 주문이 있어 신규 주문을 만들 수 없습니다.",
            "retryable": False,
            "details": {"market": "KRW-XRP"},
        },
    }


def test_state_change_request_requires_operator_context() -> None:
    request = StateChangeRequest(
        request_id="req-1",
        idempotency_key="idem-1",
        operator_id="local-user",
        reason="운영상 필요한 사유",
    )

    assert request.request_id == "req-1"
    assert request.idempotency_key == "idem-1"
    assert request.operator_id == "local-user"
    assert request.reason == "운영상 필요한 사유"

    with pytest.raises(ValueError, match="reason"):
        StateChangeRequest(
            request_id="req-1",
            idempotency_key="idem-1",
            operator_id="local-user",
            reason="",
        )


def test_utc_isoformat_requires_timezone_aware_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_isoformat(datetime(2026, 5, 31, 0, 0))


