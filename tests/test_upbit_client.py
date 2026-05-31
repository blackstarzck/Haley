from __future__ import annotations

from dataclasses import dataclass

from haley.upbit import UpbitAuth, UpbitRestClient


@dataclass
class FakeResponse:
    payload: object

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/v1/market/all"):
            return FakeResponse([{"market": "KRW-XRP"}])
        if url.endswith("/v1/ticker/all"):
            return FakeResponse([{"market": "KRW-XRP", "acc_trade_price_24h": "10"}])
        if url.endswith("/v1/accounts"):
            return FakeResponse([{"currency": "KRW", "balance": "1000000"}])
        return FakeResponse({})


def test_upbit_rest_client_fetches_public_markets_and_tickers_without_auth() -> None:
    http = FakeHttpClient()
    client = UpbitRestClient(base_url="https://api.upbit.com", http_client=http)

    markets = client.list_markets(is_details=True)
    tickers = client.list_all_tickers(quote_currencies=["KRW"])

    assert markets == [{"market": "KRW-XRP"}]
    assert tickers == [{"market": "KRW-XRP", "acc_trade_price_24h": "10"}]
    assert "Authorization" not in http.calls[0][2].get("headers", {})
    assert http.calls[0][2]["params"] == {"is_details": "true"}


def test_upbit_rest_client_fetches_accounts_with_jwt_auth_but_without_secret_leak() -> None:
    http = FakeHttpClient()
    auth = UpbitAuth(access_key="access", secret_key="secret")
    client = UpbitRestClient(
        base_url="https://api.upbit.com",
        http_client=http,
        auth=auth,
    )

    accounts = client.list_accounts()
    headers = http.calls[-1][2]["headers"]

    assert accounts == [{"currency": "KRW", "balance": "1000000"}]
    assert headers["Authorization"].startswith("Bearer ")
    assert "secret" not in repr(headers)
    assert "nonce" not in repr(headers).lower()


def test_upbit_auth_signed_headers_redact_sensitive_values() -> None:
    auth = UpbitAuth(access_key="access", secret_key="secret")

    headers = auth.signed_headers(query_string="market=KRW-XRP")
    redacted = auth.redacted_headers(headers)

    assert headers["Authorization"].startswith("Bearer ")
    assert redacted == {"Authorization": "[REDACTED]"}
