from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"

SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_secret",
    "jwt",
    "nonce",
    "query_hash",
    "secret",
    "secret_key",
)


def mask_sensitive_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_sensitive_key(str(key)) else mask_sensitive_values(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [mask_sensitive_values(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)
