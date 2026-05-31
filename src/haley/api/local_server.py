from __future__ import annotations

from pathlib import Path

import uvicorn

from haley.api.server import create_app
from haley.state_store import StateStore
from haley.upbit import UpbitRestClient


def build_app():
    return create_app(
        StateStore.open(Path("data") / "haley.sqlite3"),
        ticker_client=UpbitRestClient(base_url="https://api.upbit.com"),
    )


def main() -> None:
    uvicorn.run(build_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
