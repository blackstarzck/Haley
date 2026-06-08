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
        if url.endswith("/v1/candles/minutes/5"):
            return FakeResponse(
                [
                    {
                        "market": "KRW-XRP",
                        "candle_date_time_utc": "2026-05-31T00:00:00",
                        "opening_price": 500,
                        "high_price": 510,
                        "low_price": 490,
                        "trade_price": 505,
                        "candle_acc_trade_volume": 123,
                    }
                ]
            )
        if url.endswith("/v1/accounts"):
            return FakeResponse([{"currency": "KRW", "balance": "1000000"}])
        if url.endswith("/v1/orders/open"):
            return FakeResponse(
                [
                    {
                        "uuid": "upbit-order-1",
                        "identifier": "client-1",
                        "market": "KRW-XRP",
                    }
                ]
            )
        if url.endswith("/v1/order"):
            return FakeResponse({"identifier": "client-1", "state": "wait"})
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


def test_upbit_rest_client_fetches_public_minute_candles_without_auth() -> None:
    http = FakeHttpClient()
    client = UpbitRestClient(base_url="https://api.upbit.com", http_client=http)

    candles = client.list_minute_candles(market="KRW-XRP", unit=5, count=100)

    assert candles[0]["trade_price"] == 505
    assert http.calls[-1][1] == "https://api.upbit.com/v1/candles/minutes/5"
    assert http.calls[-1][2]["params"] == {"market": "KRW-XRP", "count": "100"}
    assert "Authorization" not in http.calls[-1][2].get("headers", {})


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


def test_upbit_client_lists_open_orders_with_auth_headers() -> None:
    http = FakeHttpClient()
    client = UpbitRestClient(
        base_url="https://api.upbit.com",
        http_client=http,
        auth=UpbitAuth(access_key="access", secret_key="secret"),
    )

    orders = client.list_open_orders()

    assert orders == [
        {"uuid": "upbit-order-1", "identifier": "client-1", "market": "KRW-XRP"}
    ]
    assert http.calls[-1][0] == "GET"
    assert http.calls[-1][1] == "https://api.upbit.com/v1/orders/open"
    assert "Authorization" in http.calls[-1][2]["headers"]


def test_upbit_client_fetches_order_detail_with_read_only_auth() -> None:
    http = FakeHttpClient()
    client = UpbitRestClient(
        base_url="https://api.upbit.com",
        http_client=http,
        auth=UpbitAuth(access_key="access", secret_key="secret"),
    )

    order = client.get_order_detail("client-1")

    assert order == {"identifier": "client-1", "state": "wait"}
    assert http.calls[-1][0] == "GET"
    assert http.calls[-1][1] == "https://api.upbit.com/v1/order"
    assert http.calls[-1][2]["params"] == {"identifier": "client-1"}
    assert "Authorization" in http.calls[-1][2]["headers"]
    assert "secret" not in repr(http.calls[-1][2]["headers"])
    assert "nonce" not in repr(http.calls[-1][2]["headers"]).lower()


def test_upbit_auth_signed_headers_redact_sensitive_values() -> None:
    auth = UpbitAuth(access_key="access", secret_key="secret")

    headers = auth.signed_headers(query_string="market=KRW-XRP")
    redacted = auth.redacted_headers(headers)

    assert headers["Authorization"].startswith("Bearer ")
    assert redacted == {"Authorization": "[REDACTED]"}
