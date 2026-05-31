from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from haley.security import REDACTED


@dataclass(frozen=True)
class UpbitAuth:
    access_key: str
    secret_key: str

    def signed_headers(self, query_string: str | None = None) -> dict[str, str]:
        payload: dict[str, str] = {
            "access_key": self.access_key,
            "nonce": str(uuid4()),
        }
        if query_string:
            payload["query_hash"] = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = _jwt_encode(payload=payload, secret_key=self.secret_key)
        return {"Authorization": f"Bearer {token}"}

    def redacted_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {key: REDACTED for key in headers}


class UpbitRestClient:
    def __init__(
        self,
        base_url: str,
        http_client: Any | None = None,
        auth: UpbitAuth | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client or httpx.Client(timeout=10)
        self._auth = auth

    def list_markets(self, is_details: bool = False) -> list[dict[str, Any]]:
        response = self._http.get(
            f"{self._base_url}/v1/market/all",
            params={"is_details": "true" if is_details else "false"},
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        return list(response.json())

    def list_all_tickers(self, quote_currencies: list[str]) -> list[dict[str, Any]]:
        params = {"quote_currencies": ",".join(quote_currencies)}
        response = self._http.get(
            f"{self._base_url}/v1/ticker/all",
            params=params,
            headers={"accept": "application/json"},
        )
        response.raise_for_status()
        return list(response.json())

    def list_accounts(self) -> list[dict[str, Any]]:
        if self._auth is None:
            raise RuntimeError("Upbit account lookup requires auth")
        headers = {
            "accept": "application/json",
            **self._auth.signed_headers(),
        }
        response = self._http.get(f"{self._base_url}/v1/accounts", headers=headers)
        response.raise_for_status()
        return list(response.json())


def _jwt_encode(payload: dict[str, str], secret_key: str) -> str:
    header = {"alg": "HS512", "typ": "JWT"}
    signing_input = (
        _base64url_json(header) + "." + _base64url_json(payload)
    ).encode("ascii")
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha512,
    ).digest()
    return f"{signing_input.decode('ascii')}.{_base64url(signature)}"


def _base64url_json(value: dict[str, str]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url(encoded)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def build_query_string(params: dict[str, Any]) -> str:
    return urlencode(params, doseq=True)
