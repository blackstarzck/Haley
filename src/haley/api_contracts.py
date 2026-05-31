from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _server_time(value: datetime | None) -> datetime:
    return datetime.now(UTC) if value is None else value


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text("code", self.code)
        _require_text("message", self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class StateChangeRequest:
    request_id: str
    idempotency_key: str
    operator_id: str
    reason: str

    def __post_init__(self) -> None:
        _require_text("request_id", self.request_id)
        _require_text("idempotency_key", self.idempotency_key)
        _require_text("operator_id", self.operator_id)
        _require_text("reason", self.reason)


class ApiResponse:
    @staticmethod
    def success(
        data: dict[str, Any],
        request_id: str,
        server_time: datetime | None = None,
    ) -> dict[str, Any]:
        _require_text("request_id", request_id)
        return {
            "server_time": utc_isoformat(_server_time(server_time)),
            "request_id": request_id,
            "data": data,
        }

    @staticmethod
    def error(
        request_id: str,
        error: ApiError,
        server_time: datetime | None = None,
    ) -> dict[str, Any]:
        _require_text("request_id", request_id)
        return {
            "server_time": utc_isoformat(_server_time(server_time)),
            "request_id": request_id,
            "error": error.to_dict(),
        }
