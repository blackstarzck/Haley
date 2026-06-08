# PAPER 실험 플랫폼 보완 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 PAPER 자동매매 MVP를 실제 실험 기록 기반 전략 보완과 LIVE 전환 검증이 가능한 운영 시스템으로 보강하되, 1차 릴리스에서는 LIVE 실제 주문을 열지 않는다.

**Architecture:** 안전 상태를 `StateStore`에 영속화하고, `PaperRunner`는 매 tick마다 최신 운영 모드와 리스크 상태를 읽는다. 복구, DRY_RUN, 실험 세션, 전략 저널, 콘솔 UX를 단계적으로 추가하되, 실제 주문 API는 별도 승인 전까지 코드와 테스트 양쪽에서 명시적으로 잠근다. 이 계획의 목표는 LIVE 구현이 아니라 PAPER 운영 검증과 LIVE 잠금 유지다.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest, 정적 HTML 운영 콘솔

---

## 전체 Phase 요약

| Phase | 이름 | 목표 |
|---:|---|---|
| 0 | 현재 상태 정리와 기준 테스트 | 현재 DB 차단 상태와 테스트 기준을 명확히 한다. |
| 1 | 운영 모드/킬스위치 영속화 | 실행 중인 PAPER Runner가 최신 킬스위치를 즉시 반영하게 한다. |
| 2 | 복구/대조 API 실제 연결 | 더미 복구 API를 실제 `RecoveryManager` 기반 흐름으로 바꾼다. |
| 3 | DRY_RUN 실효성 강화와 LIVE 잠금 | 실제 주문 전 검증과 실거래 차단을 명시적으로 구현한다. |
| 4 | PAPER 리스크 지표와 상태 초기화 | 잔고 부족, 노출, 일손실, 실험 리셋 정책을 구현한다. |
| 5 | 실험 세션과 전략 저널 | 실험 결과를 전략 보완에 쓸 수 있게 저장한다. |
| 6 | 운영 콘솔 안전 UX | 차단 사유, 다음 행동, 확인 모달, 승격 상태를 화면에 반영한다. |
| 7 | 전략 검증 고도화 | Zone 상태, 체결 비교, 백테스트-페이퍼 비교를 추가한다. |

## 공통 개발 원칙

- 실제 주문 API 호출은 이 계획 전체에서 열지 않는다.
- 각 Phase는 테스트를 먼저 추가하고, 실패를 확인한 뒤 구현한다.
- 돈, 수량, 수수료, PnL은 `Decimal` 또는 문자열 기반으로 다룬다.
- 민감값은 DB, 감사 로그, API 응답, 예외 메시지에 남기지 않는다.
- 각 Phase 완료 후 최소 검증 명령은 `python -m pytest`다.

## P0 안전 보강 기준

아래 항목은 Phase 1 구현 전에 먼저 계획에 반영해야 하는 안전 보강이다.
기존 Phase의 목표와 겹치더라도, 실제 주문 차단과 복구 후 자동 재개 금지는 별도 테스트로 못 박는다.

| 보강 ID | 영역 | 반드시 닫아야 하는 위험 |
|---|---|---|
| SG-01 | 실제 주문 API 잠금 | 설정값 확인이 아니라 주문 생성/취소 함수 호출 시도 자체가 차단되고 HTTP 호출이 0건이어야 한다. |
| SG-02 | 복구 후 재개 정책 | `MATCHED`가 되어도 운영자 재개 승인 전에는 신규 주문을 만들 수 없어야 한다. |
| SG-03 | UNKNOWN 대조 | `UNKNOWN`, `SUBMITTING`, `PARTIALLY_FILLED`, `CANCEL_FAILED` 주문은 원래 `identifier`와 잔고/locked 대조 전까지 같은 마켓 신규 진입을 막아야 한다. |
| SG-04 | DRY_RUN 실효성 | 최소 주문금액뿐 아니라 주문 타입별 필드, KRW 호가 단위, 숫자 문자열 직렬화, 권한 오류를 검증해야 한다. |
| SG-05 | 리스크 지표 연결 | 일손실, 연속 손절, 종목별 노출, 전체 노출, 잔고 동기화 실패가 `PaperRunner` 실행 경로에 연결되어야 한다. |
| SG-06 | 원자적 저장 | 주문, 체결, 포지션, 포트폴리오 갱신은 장애 중간 상태가 남지 않도록 하나의 트랜잭션 단위로 묶어야 한다. |
| SG-07 | 민감정보 마스킹 | `Authorization`, JWT, Secret, nonce, query hash가 API 응답, DB, 감사 로그, 예외 메시지에 남지 않아야 한다. |
| SG-08 | 승격 게이트 | “LIVE 전환 조건” 문구가 아니라 미충족 조건 목록을 API와 콘솔에서 확인해야 한다. |

### Safety Gate 1: 실제 주문 게이트웨이 명시 잠금

**목표:** 아직 실제 주문 기능을 열지 않더라도, 주문 생성/취소 경로가 생겼을 때 기본값에서 반드시 실패하고 HTTP 호출이 0건임을 테스트한다.

**Files:**
- Create: `src/haley/order_gateway.py`
- Test: `tests/test_order_gateway.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_order_gateway.py`:

```python
from decimal import Decimal

import pytest

from haley.domain import ModeState, OrderSide, OrderType, RuntimeMode
from haley.order_gateway import RealOrderGateway


class SpyHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> object:
        self.calls.append(("POST", url, kwargs))
        raise AssertionError("real order HTTP call must not happen")

    def delete(self, url: str, **kwargs: object) -> object:
        self.calls.append(("DELETE", url, kwargs))
        raise AssertionError("real cancel HTTP call must not happen")


@pytest.mark.parametrize(
    "mode",
    [
        ModeState(mode=RuntimeMode.PAPER, paper_allow_real_order_api=False),
        ModeState(mode=RuntimeMode.DRY_RUN),
        ModeState(mode=RuntimeMode.RECOVERY_ONLY),
        ModeState(mode=RuntimeMode.KILL_SWITCHED, kill_switch_enabled=True),
        ModeState(mode=RuntimeMode.LIVE, live_trading_enabled=False),
    ],
)
def test_real_order_gateway_never_calls_http_when_locked(mode: ModeState) -> None:
    http = SpyHttpClient()
    gateway = RealOrderGateway(base_url="https://api.upbit.com", http_client=http, mode=mode)

    with pytest.raises(RuntimeError, match="LIVE trading is disabled"):
        gateway.create_order(
            market="KRW-XRP",
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            volume=Decimal("10"),
            price=Decimal("500"),
            identifier="client-1",
        )

    assert http.calls == []


def test_real_cancel_gateway_never_calls_http_when_locked() -> None:
    http = SpyHttpClient()
    gateway = RealOrderGateway(base_url="https://api.upbit.com", http_client=http, mode=ModeState())

    with pytest.raises(RuntimeError, match="LIVE trading is disabled"):
        gateway.cancel_order(identifier="client-1")

    assert http.calls == []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_order_gateway.py -v
```

Expected:

```text
FAIL because haley.order_gateway does not exist
```

- [ ] **Step 3: 최소 구현**

Create `src/haley/order_gateway.py`:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Any

from haley.domain import ModeState, OrderSide, OrderType


class RealOrderGateway:
    def __init__(self, base_url: str, http_client: Any, mode: ModeState) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._mode = mode

    def create_order(
        self,
        *,
        market: str,
        side: OrderSide,
        order_type: OrderType,
        volume: Decimal | None,
        price: Decimal | None,
        identifier: str,
    ) -> dict[str, Any]:
        self._raise_if_locked()
        raise RuntimeError("real order API is not implemented in first release")

    def cancel_order(self, *, identifier: str) -> dict[str, Any]:
        self._raise_if_locked()
        raise RuntimeError("real cancel API is not implemented in first release")

    def _raise_if_locked(self) -> None:
        if not self._mode.allows_real_order_api:
            raise RuntimeError("LIVE trading is disabled")
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_order_gateway.py -v
```

Expected:

```text
PASSED
```

### Safety Gate 2: 복구 완료 후 운영자 승인 전 자동 재개 금지

**목표:** 복구 결과가 `MATCHED`여도 운영자가 재개 버튼을 누르기 전까지 `RiskManager`가 신규 진입을 막게 한다.

**Files:**
- Modify: `src/haley/domain.py`
- Modify: `src/haley/state_store.py`
- Modify: `src/haley/risk.py`
- Test: `tests/test_risk_manager.py`
- Test: `tests/test_state_store_operational_records.py`

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_risk_manager.py`:

```python
from haley.domain import ModeState, ReconciliationState, ReconciliationStatus, RiskBlockReason
from haley.risk import RiskContext, RiskManager
from haley.state_store import StateStore


def test_recovery_matched_still_blocks_until_operator_resume() -> None:
    store = StateStore.in_memory()
    store.save_reconciliation_state(
        ReconciliationState(
            status=ReconciliationStatus.MATCHED,
            mismatch_count=0,
            operator_resume_required=True,
        )
    )

    decision = RiskManager(store).evaluate_new_entry(RiskContext(mode=ModeState()))

    assert decision.allowed is False
    assert RiskBlockReason.RECOVERY_INCOMPLETE in decision.reasons
```

Add to `tests/test_state_store_operational_records.py`:

```python
from haley.domain import ReconciliationState, ReconciliationStatus


def test_reconciliation_state_persists_operator_resume_required() -> None:
    store = StateStore.in_memory()
    store.save_reconciliation_state(
        ReconciliationState(
            status=ReconciliationStatus.MATCHED,
            mismatch_count=0,
            operator_resume_required=True,
        )
    )

    loaded = store.get_reconciliation_state()

    assert loaded.status is ReconciliationStatus.MATCHED
    assert loaded.operator_resume_required is True
    assert loaded.allows_new_entry is False
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_risk_manager.py::test_recovery_matched_still_blocks_until_operator_resume tests/test_state_store_operational_records.py::test_reconciliation_state_persists_operator_resume_required -v
```

Expected:

```text
FAIL because ReconciliationState has no operator_resume_required field
```

- [ ] **Step 3: 구현**

Modify `src/haley/domain.py`:

```python
@dataclass(frozen=True)
class ReconciliationState:
    status: ReconciliationStatus = ReconciliationStatus.NOT_STARTED
    mismatch_count: int = 0
    last_checked_at: datetime | None = None
    operator_resume_required: bool = False

    @property
    def allows_new_entry(self) -> bool:
        return (
            self.status is ReconciliationStatus.MATCHED
            and self.mismatch_count == 0
            and not self.operator_resume_required
        )
```

Modify the `reconciliation_state` schema and save/load methods in `src/haley/state_store.py`:

```sql
operator_resume_required INTEGER NOT NULL DEFAULT 0
```

When saving:

```python
1 if state.operator_resume_required else 0
```

When loading:

```python
operator_resume_required=bool(row["operator_resume_required"]),
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_risk_manager.py tests/test_state_store_operational_records.py -v
```

Expected:

```text
All selected tests pass
```

### Safety Gate 3: UNKNOWN 주문 대조 전 신규 진입 0건 보장

**목표:** 같은 마켓에 미확정 주문이 있으면 신호가 있어도 `PaperRunner`가 새 주문을 만들지 않게 한다.

**Files:**
- Modify: `src/haley/paper_runner.py`
- Test: `tests/test_paper_runner.py`
- Test: `tests/test_order_coordinator.py`

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_paper_runner.py`:

```python
from haley.domain import OrderStatus


def test_paper_runner_does_not_order_when_unknown_order_exists_for_market() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    existing = OrderCoordinator(store).create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier="client-existing",
        state_change=StateChangeRequest(
            request_id="req-existing",
            idempotency_key="idem-existing",
            operator_id="tester",
            reason="unknown order guard",
        ),
    )
    OrderCoordinator(store).transition_order(
        existing.order_id,
        OrderStatus.SUBMITTING,
        StateChangeRequest(
            request_id="req-submit",
            idempotency_key="idem-submit",
            operator_id="tester",
            reason="submitting",
        ),
    )
    OrderCoordinator(store).transition_order(
        existing.order_id,
        OrderStatus.UNKNOWN,
        StateChangeRequest(
            request_id="req-unknown",
            idempotency_key="idem-unknown",
            operator_id="tester",
            reason="timeout",
        ),
    )

    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)

    state = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    ).tick()

    assert state.last_action == "BLOCKED"
    assert len(store.list_orders()) == 1
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py::test_paper_runner_does_not_order_when_unknown_order_exists_for_market -v
```

Expected:

```text
FAIL if PaperRunner bypasses OrderCoordinator duplicate guard
```

- [ ] **Step 3: 구현 기준**

`PaperRunner`는 직접 주문을 만들기 전 반드시 `OrderCoordinator.create_entry_order()`를 거쳐야 한다.
`OrderCoordinator`는 `blocks_new_entry_statuses()`에 포함된 주문 상태가 같은 마켓에 있으면 예외 또는 `BLOCKED` 상태를 반환해야 한다.

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py tests/test_order_coordinator.py -v
```

Expected:

```text
All selected tests pass
```

### Safety Gate 4: 리스크 지표를 PAPER 실행 경로에 연결

**목표:** `RiskMetrics`가 정의만 되어 있는 상태를 끝내고, `PaperRunner.tick()`이 실제 포트폴리오와 포지션에서 지표를 만들어 `RiskContext`에 넘기게 한다.

**Files:**
- Modify: `src/haley/risk.py`
- Modify: `src/haley/paper_runner.py`
- Test: `tests/test_risk_manager.py`
- Test: `tests/test_paper_runner.py`

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_paper_runner.py`:

```python
def test_paper_runner_blocks_when_symbol_exposure_limit_is_exceeded() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("1000"),
            average_entry_price=Decimal("500"),
            stop_protected=True,
            stop_price=Decimal("450"),
        )
    )
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )

    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)

    state = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    ).tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "EXPOSURE_LIMIT"
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py::test_paper_runner_blocks_when_symbol_exposure_limit_is_exceeded -v
```

Expected:

```text
FAIL because PaperRunner does not pass RiskMetrics to RiskContext
```

- [ ] **Step 3: 구현**

Add a helper in `src/haley/paper_runner.py`:

```python
def _risk_metrics(self) -> RiskMetrics:
    portfolio = self._store.get_paper_portfolio()
    positions = self._store.list_positions()
    equity = portfolio.cash_krw + portfolio.locked_cash_krw
    symbol_exposure: dict[str, Decimal] = {}
    total_exposure = Decimal("0")
    for position in positions:
        price = self._price_by_market.get(position.market, position.average_entry_price)
        exposure = position.volume * price
        symbol_exposure[position.market] = exposure
        total_exposure += exposure
        equity += exposure
    return RiskMetrics(
        account_equity=equity,
        symbol_exposure=symbol_exposure,
        total_crypto_exposure=total_exposure,
        balance_synced=True,
        order_permission_ok=True,
    )
```

Pass it into `RiskContext`:

```python
decision = self._risk_manager.evaluate_new_entry(
    RiskContext(
        mode=mode,
        data_quality=quality,
        market=market,
        metrics=self._risk_metrics(),
    )
)
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py tests/test_risk_manager.py -v
```

Expected:

```text
All selected tests pass
```

### Safety Gate 5: 원자적 저장 경계 추가

**목표:** PAPER 체결과 실험 리셋이 중간 실패 시 부분 상태를 남기지 않게 한다.

**Files:**
- Modify: `src/haley/state_store.py`
- Modify: `src/haley/paper.py`
- Modify: `src/haley/api/server.py`
- Test: `tests/test_state_store_operational_records.py`
- Test: `tests/test_paper_trading.py`

- [ ] **Step 1: 리셋 원자성 실패 테스트 작성**

Add to `tests/test_state_store_operational_records.py`:

```python
def test_reset_paper_experiment_state_resets_portfolio_in_one_store_call() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
        )
    )

    portfolio = store.reset_paper_experiment_state(initial_cash_krw=Decimal("2000000"))

    assert portfolio.cash_krw == Decimal("2000000")
    assert portfolio.locked_cash_krw == Decimal("0")
    assert store.list_positions() == []
    assert store.list_orders() == []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_state_store_operational_records.py::test_reset_paper_experiment_state_resets_portfolio_in_one_store_call -v
```

Expected:

```text
FAIL because reset_paper_experiment_state does not accept initial_cash_krw or return portfolio
```

- [ ] **Step 3: 구현 기준**

`src/haley/state_store.py`의 `reset_paper_experiment_state()`는 삭제와 포트폴리오 초기화를 하나의 메서드 안에서 처리한다.

```python
def reset_paper_experiment_state(self, initial_cash_krw: Decimal) -> PaperPortfolio:
    portfolio = PaperPortfolio(initial_cash_krw=initial_cash_krw)
    with self._lock:
        with self._connection:
            self._connection.execute("DELETE FROM fills")
            self._connection.execute("DELETE FROM orders")
            self._connection.execute("DELETE FROM positions")
            self._connection.execute("DELETE FROM stop_protections")
            self._connection.execute("DELETE FROM risk_blocks")
            self._connection.execute("DELETE FROM alerts")
            self._connection.execute("DELETE FROM data_quality_states")
            self._connection.execute("DELETE FROM reconciliation_state")
            self._save_paper_portfolio_unlocked(portfolio)
    return portfolio
```

`save_paper_portfolio()` 내부 SQL은 `_save_paper_portfolio_unlocked()`로 분리해 재사용한다.

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_state_store_operational_records.py tests/test_paper_trading.py -v
```

Expected:

```text
All selected tests pass
```

### Safety Gate 6: 승격 게이트와 성과 리포트 기준 추가

**목표:** 콘솔이 “LIVE 전환 조건”이라는 문구만 보여주는 상태를 끝내고, 실제 미충족 조건 목록을 보여준다.

**Files:**
- Create: `src/haley/promotion.py`
- Modify: `src/haley/api/server.py`
- Modify: `web/operations-console.html`
- Test: `tests/test_promotion.py`
- Test: `tests/test_api_server.py`
- Test: `tests/test_operations_console_ui.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `tests/test_promotion.py`:

```python
from dataclasses import dataclass

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
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_promotion.py -v
```

Expected:

```text
FAIL because haley.promotion does not exist
```

- [ ] **Step 3: 구현**

Create `src/haley/promotion.py`:

```python
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
```

- [ ] **Step 4: API와 콘솔 연결**

Add `/api/promotion/status` in `src/haley/api/server.py` and render `unmet_conditions` in `web/operations-console.html`.
콘솔에는 최소한 아래 문구가 실제 API 응답 기반으로 보여야 한다.

```text
LIVE 전환 조건 미충족
PAPER_RUNTIME_DAYS_LT_28
PAPER_SIGNAL_COUNT_LT_200
DRY_RUN_NOT_PASSED
```

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_promotion.py tests/test_api_server.py tests/test_operations_console_ui.py -v
```

Expected:

```text
All selected tests pass
```

---

## Phase 0: 현재 상태 정리와 기준 테스트

**목표:** 현재 운영 DB가 차단 상태인 이유를 문서화하고, 개발 전 테스트 기준을 고정한다.

**Files:**
- Create: `docs/handoff/phase-09-fix-plan-baseline.md`
- Modify: 없음
- Test: 없음

### Task 0.1: 운영 DB 상태 스냅샷 문서화

- [ ] **Step 1: 현재 상태 조회**

Run:

```powershell
@'
from pathlib import Path
from haley.state_store import StateStore

store = StateStore.open(Path("data") / "haley.sqlite3")
print("orders", [(o.intent.market, o.status.value) for o in store.list_orders()])
print("positions", [(p.market, str(p.volume), p.stop_protected, str(p.stop_price)) for p in store.list_positions()])
print("risk_blocks_count", len(store.list_risk_blocks()))
print("reconciliation", store.get_reconciliation_state().status.value, store.get_reconciliation_state().allows_new_entry)
'@ | python -
```

Expected:

```text
현재 운영 DB 상태가 출력된다.
보호 없는 포지션이 있으면 신규 진입이 차단되는 것이 정상이다.
```

- [ ] **Step 2: 기준 테스트 실행**

Run:

```powershell
python -m pytest
python -m compileall src tests
```

Expected:

```text
pytest: all tests pass
compileall: exit code 0
```

- [ ] **Step 3: 문서 작성**

`docs/handoff/phase-09-fix-plan-baseline.md`에 아래 내용을 기록한다.

```markdown
# Phase 09 Fix Plan Baseline

작성일: 2026-06-07

## 현재 운영 DB 상태

- 주문:
- 포지션:
- 리스크 블록 수:
- 대조 상태:

## 기준 검증

- `python -m pytest`:
- `python -m compileall src tests`:

## 해석

현재 운영 DB에 보호 없는 포지션이 있으면 신규 주문 차단은 정상 동작이다.
기능 개선은 운영 DB를 임의 삭제하지 않고 테스트 DB와 인메모리 저장소 중심으로 진행한다.
```

---

## Phase 1: 운영 모드/킬스위치 영속화

**목표:** API에서 킬스위치를 켜면 실행 중인 `PaperRunner`가 다음 tick부터 신규 주문을 만들지 못하게 한다.

**Files:**
- Modify: `src/haley/state_store.py`
- Modify: `src/haley/api/server.py`
- Modify: `src/haley/paper_runner.py`
- Test: `tests/test_state_store_operational_records.py`
- Test: `tests/test_api_server.py`
- Test: `tests/test_paper_runner.py`

### Task 1.1: `ModeState` 저장/조회 기능 추가

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_state_store_operational_records.py`:

```python
from haley.domain import ModeState, RuntimeMode


def test_mode_state_can_be_saved_and_loaded() -> None:
    store = StateStore.in_memory()
    state = ModeState(
        mode=RuntimeMode.KILL_SWITCHED,
        live_trading_enabled=False,
        paper_allow_real_order_api=False,
        kill_switch_enabled=True,
    )

    store.save_mode_state(state)
    loaded = store.get_mode_state()

    assert loaded.mode is RuntimeMode.KILL_SWITCHED
    assert loaded.kill_switch_enabled is True
    assert loaded.live_trading_enabled is False
    assert loaded.paper_allow_real_order_api is False
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_state_store_operational_records.py::test_mode_state_can_be_saved_and_loaded -v
```

Expected:

```text
FAIL: StateStore has no attribute save_mode_state
```

- [ ] **Step 3: 구현**

Modify `src/haley/state_store.py`:

```python
def save_mode_state(self, state: ModeState) -> None:
    with self._connection:
        self._connection.execute(
            """
            INSERT INTO mode_state (
                singleton_id,
                mode,
                live_trading_enabled,
                paper_allow_real_order_api,
                kill_switch_enabled,
                updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(singleton_id) DO UPDATE SET
                mode = excluded.mode,
                live_trading_enabled = excluded.live_trading_enabled,
                paper_allow_real_order_api = excluded.paper_allow_real_order_api,
                kill_switch_enabled = excluded.kill_switch_enabled,
                updated_at = excluded.updated_at
            """,
            (
                state.mode.value,
                1 if state.live_trading_enabled else 0,
                1 if state.paper_allow_real_order_api else 0,
                1 if state.kill_switch_enabled else 0,
                state.updated_at.isoformat(),
            ),
        )


def get_mode_state(self) -> ModeState:
    row = self._connection.execute(
        "SELECT * FROM mode_state WHERE singleton_id = 1"
    ).fetchone()
    if row is None:
        return ModeState()
    return ModeState(
        mode=RuntimeMode(row["mode"]),
        live_trading_enabled=bool(row["live_trading_enabled"]),
        paper_allow_real_order_api=bool(row["paper_allow_real_order_api"]),
        kill_switch_enabled=bool(row["kill_switch_enabled"]),
        updated_at=_datetime_from_text(row["updated_at"]),
    )
```

Also add schema inside `_initialize_schema()`:

```sql
CREATE TABLE IF NOT EXISTS mode_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    mode TEXT NOT NULL,
    live_trading_enabled INTEGER NOT NULL,
    paper_allow_real_order_api INTEGER NOT NULL,
    kill_switch_enabled INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_state_store_operational_records.py::test_mode_state_can_be_saved_and_loaded -v
```

Expected:

```text
PASSED
```

### Task 1.2: API 킬스위치를 Store에 저장

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_api_server.py`:

```python
from haley.domain import RuntimeMode


def test_kill_switch_enable_persists_mode_state() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    response = client.post(
        "/api/kill-switch/enable",
        json={
            "request_id": "req-kill",
            "idempotency_key": "idem-kill",
            "operator_id": "local-user",
            "reason": "manual stop",
        },
    )

    assert response.status_code == 200
    saved = store.get_mode_state()
    assert saved.mode is RuntimeMode.KILL_SWITCHED
    assert saved.kill_switch_enabled is True
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_kill_switch_enable_persists_mode_state -v
```

Expected:

```text
FAIL before API persists mode state
```

- [ ] **Step 3: 구현**

Modify `/api/kill-switch/enable` in `src/haley/api/server.py`:

```python
state.mode = ModeState(
    mode=RuntimeMode.KILL_SWITCHED,
    live_trading_enabled=False,
    paper_allow_real_order_api=False,
    kill_switch_enabled=True,
)
store.save_mode_state(state.mode)
```

Modify app startup after `state = runtime or ApiRuntimeState()`:

```python
state.mode = store.get_mode_state()
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_kill_switch_enable_persists_mode_state -v
```

Expected:

```text
PASSED
```

### Task 1.3: PaperRunner가 매 tick 최신 모드 읽기

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_paper_runner.py`:

```python
from haley.domain import RuntimeMode


def test_paper_runner_reads_latest_kill_switch_before_ordering() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.save_reconciliation_state(ReconciliationState(status=ReconciliationStatus.MATCHED))
    store.upsert_data_quality_state(
        "KRW-XRP",
        DataQualityState(stale=False, rest_ws_mismatch=False),
    )
    candle_store = CandleStore()
    for item in ufs_r1_signal_candles("KRW-XRP"):
        candle_store.upsert(item)
    runner = PaperRunner(
        store=store,
        selected_markets=["KRW-XRP"],
        price_by_market={"KRW-XRP": Decimal("500")},
        candle_store=candle_store,
    )
    store.save_mode_state(
        ModeState(
            mode=RuntimeMode.KILL_SWITCHED,
            live_trading_enabled=False,
            paper_allow_real_order_api=False,
            kill_switch_enabled=True,
        )
    )

    state = runner.tick()

    assert state.last_action == "BLOCKED"
    assert state.last_block_reason == "KILL_SWITCH_ON"
    assert store.list_orders() == []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py::test_paper_runner_reads_latest_kill_switch_before_ordering -v
```

Expected:

```text
FAIL because runner still uses constructor mode
```

- [ ] **Step 3: 구현**

Modify `src/haley/paper_runner.py` inside `tick()` before risk evaluation:

```python
mode = self._store.get_mode_state()
```

Then pass this mode to `RiskContext`:

```python
decision = self._risk_manager.evaluate_new_entry(
    RiskContext(
        mode=mode,
        data_quality=quality,
        market=market,
    )
)
```

Also update state mode when returning:

```python
self._mode = mode
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_paper_runner.py::test_paper_runner_reads_latest_kill_switch_before_ordering -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: Phase 검증**

Run:

```powershell
python -m pytest tests/test_state_store_operational_records.py tests/test_api_server.py tests/test_paper_runner.py -v
```

Expected:

```text
All selected tests pass
```

---

## Phase 2: 복구/대조 API 실제 연결

**목표:** `/api/recovery/run`이 더미 응답이 아니라 실제 복구 매니저를 실행하고 완료 상태를 저장하게 한다. 단, 복구 결과가 `MATCHED`여도 운영자 재개 승인 전에는 신규 주문을 허용하지 않는다.

**Files:**
- Modify: `src/haley/recovery.py`
- Modify: `src/haley/upbit.py`
- Modify: `src/haley/api/server.py`
- Test: `tests/test_recovery.py`
- Test: `tests/test_api_server.py`
- Test: `tests/test_upbit_client.py`

### Task 2.0: 현재 `RecoveryRun` 모델 정렬

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_recovery.py`:

```python
def test_recovery_run_exposes_run_id_and_reconciliation_status() -> None:
    store = StateStore.in_memory()
    exchange = FakeExchange(accounts=[], open_orders=[])

    run = RecoveryManager(store=store, exchange=exchange).run()

    assert run.recovery_run_id.startswith("recovery_")
    assert run.reconciliation_status is ReconciliationStatus.MATCHED
    assert run.status is RecoveryStepStatus.SUCCEEDED
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_recovery.py::test_recovery_run_exposes_run_id_and_reconciliation_status -v
```

Expected:

```text
FAIL because RecoveryRun currently has no recovery_run_id or reconciliation_status
```

- [ ] **Step 3: 구현**

Modify `src/haley/recovery.py`:

```python
from uuid import uuid4
```

```python
@dataclass(frozen=True)
class RecoveryRun:
    recovery_run_id: str
    status: RecoveryStepStatus
    reconciliation_status: ReconciliationStatus
    steps: list[RecoveryStep]
```

At the start of `RecoveryManager.run()`:

```python
recovery_run_id = f"recovery_{uuid4().hex}"
```

Every `RecoveryRun` return value must include `recovery_run_id` and `reconciliation_status`.
Failure returns use `reconciliation_status=ReconciliationStatus.FAILED`.

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_recovery.py -v
```

Expected:

```text
All recovery tests pass
```

### Task 2.1: `RecoveryManager.run()` 완료 상태 명확화

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_recovery.py`:

```python
def test_recovery_manager_marks_matched_but_requires_operator_resume_when_no_mismatches() -> None:
    store = StateStore.in_memory()
    exchange = FakeExchange(accounts=[], open_orders=[])
    manager = RecoveryManager(store=store, exchange=exchange)

    run = manager.run()
    saved = store.get_reconciliation_state()

    assert run.reconciliation_status is ReconciliationStatus.MATCHED
    assert saved.status is ReconciliationStatus.MATCHED
    assert saved.operator_resume_required is True
    assert saved.allows_new_entry is False
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_recovery.py::test_recovery_manager_marks_matched_but_requires_operator_resume_when_no_mismatches -v
```

Expected:

```text
FAIL because current recovery remains RUNNING or does not track operator resume requirement
```

- [ ] **Step 3: 구현**

Modify `src/haley/recovery.py`:

```python
final_status = (
    ReconciliationStatus.MATCHED
    if mismatch_count == 0
    else ReconciliationStatus.MISMATCHED
)
self._store.save_reconciliation_state(
    ReconciliationState(
        status=final_status,
        mismatch_count=mismatch_count,
        last_checked_at=datetime.now(UTC),
        operator_resume_required=final_status is ReconciliationStatus.MATCHED,
    )
)
return RecoveryRun(
    recovery_run_id=recovery_run_id,
    reconciliation_status=final_status,
    status=RecoveryStepStatus.SUCCEEDED if final_status is ReconciliationStatus.MATCHED else RecoveryStepStatus.FAILED,
    steps=steps,
)
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_recovery.py -v
```

Expected:

```text
All recovery tests pass
```

### Task 2.2: Upbit read-only 복구 메서드 추가

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_upbit_client.py`:

```python
def test_upbit_client_lists_open_orders_with_auth_headers() -> None:
    http = FakeHttpClient()
    client = UpbitRestClient(
        base_url="https://api.upbit.com",
        http_client=http,
        auth=UpbitAuth(access_key="access", secret_key="secret"),
    )

    orders = client.list_open_orders()

    assert orders == [{"uuid": "upbit-order-1", "identifier": "client-1", "market": "KRW-XRP"}]
    assert http.calls[-1][0] == "GET"
    assert http.calls[-1][1] == "https://api.upbit.com/v1/orders/open"
    assert "Authorization" in http.calls[-1][2]["headers"]
```

Update `FakeHttpClient.get()` in `tests/test_upbit_client.py`:

```python
if url.endswith("/v1/orders/open"):
    return FakeResponse(
        [{"uuid": "upbit-order-1", "identifier": "client-1", "market": "KRW-XRP"}]
    )
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_upbit_client.py::test_upbit_client_lists_open_orders_with_auth_headers -v
```

Expected:

```text
FAIL because list_open_orders is not implemented
```

- [ ] **Step 3: 구현**

Modify `src/haley/upbit.py`:

```python
def list_open_orders(self) -> list[dict[str, Any]]:
    if self._auth is None:
        raise RuntimeError("Upbit open order lookup requires auth")
    headers = {
        "accept": "application/json",
        **self._auth.signed_headers(),
    }
    response = self._http.get(f"{self._base_url}/v1/orders/open", headers=headers)
    response.raise_for_status()
    return list(response.json())
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_upbit_client.py -v
```

Expected:

```text
All Upbit client tests pass
```

### Task 2.3: Recovery API와 Manager 연결

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_api_server.py`:

```python
def test_recovery_run_api_updates_reconciliation_state_without_auto_resume() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store, recovery_exchange=FakeRecoveryExchange()))

    body = client.post(
        "/api/recovery/run",
        json={
            "request_id": "req-recovery",
            "idempotency_key": "idem-recovery",
            "operator_id": "local-user",
            "reason": "startup recovery",
        },
    ).json()

    assert body["data"]["status"] == "MATCHED"
    assert store.get_reconciliation_state().status is ReconciliationStatus.MATCHED
    assert store.get_reconciliation_state().allows_new_entry is False
    assert body["data"]["operator_resume_required"] is True
```

Add helper in the same test file:

```python
class FakeRecoveryExchange:
    def list_accounts(self) -> list[dict[str, object]]:
        return []

    def list_open_orders(self) -> list[dict[str, object]]:
        return []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_recovery_run_api_updates_reconciliation_state_without_auto_resume -v
```

Expected:

```text
FAIL because create_app does not accept recovery_exchange or API returns running dummy state
```

- [ ] **Step 3: 구현**

Modify `create_app()` signature in `src/haley/api/server.py`:

```python
def create_app(
    store: StateStore,
    runtime: ApiRuntimeState | None = None,
    ticker_client: Any | None = None,
    recovery_exchange: Any | None = None,
) -> FastAPI:
```

Modify `/api/recovery/run`:

```python
if recovery_exchange is None:
    recovery_run_id = f"recovery_{uuid4().hex}"
    run = {
        "recovery_run_id": recovery_run_id,
        "status": "FAILED",
        "current_step": "exchange_not_configured",
    }
    state.recovery_runs[recovery_run_id] = run
    store.save_reconciliation_state(
        ReconciliationState(status=ReconciliationStatus.FAILED)
    )
    return ApiResponse.success(request_id=body.request_id, data=run)

manager = RecoveryManager(store=store, exchange=recovery_exchange)
recovery_run = manager.run()
run = {
    "recovery_run_id": recovery_run.recovery_run_id,
    "status": recovery_run.reconciliation_status.value,
    "current_step": None,
    "operator_resume_required": True,
}
state.recovery_runs[recovery_run.recovery_run_id] = run
return ApiResponse.success(request_id=body.request_id, data=run)
```

Required imports:

```python
from haley.domain import ReconciliationState, ReconciliationStatus
from haley.recovery import RecoveryManager
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_recovery_run_api_updates_reconciliation_state -v
```

Expected:

```text
PASSED
```

---

## Phase 3: DRY_RUN 실효성 강화와 LIVE 잠금

**목표:** DRY_RUN을 실제 주문 전 검증 게이트로 만들고, LIVE 주문/취소 API가 승인 전에는 절대 열리지 않게 한다.

**Files:**
- Create: `src/haley/dry_run.py`
- Modify: `src/haley/api/server.py`
- Modify: `src/haley/domain.py`
- Test: `tests/test_dry_run.py`
- Test: `tests/test_api_server.py`

### Task 3.1: DRY_RUN 검증기 추가

- [ ] **Step 1: 테스트 파일 생성**

Create `tests/test_dry_run.py`:

```python
from decimal import Decimal

from haley.dry_run import DryRunOrderValidator
from haley.domain import OrderSide, OrderType


def test_dry_run_rejects_below_minimum_krw_order() -> None:
    validator = DryRunOrderValidator(min_quote_amount=Decimal("5000"))

    result = validator.validate(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("4999"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
    )

    assert result.valid is False
    assert result.reasons == ["MIN_QUOTE_AMOUNT"]
    assert result.would_call_real_order_api is False


def test_dry_run_accepts_valid_limit_order_without_real_api() -> None:
    validator = DryRunOrderValidator(min_quote_amount=Decimal("5000"))

    result = validator.validate(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
    )

    assert result.valid is True
    assert result.reasons == []
    assert result.would_call_real_order_api is False
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_dry_run.py -v
```

Expected:

```text
FAIL because haley.dry_run does not exist
```

- [ ] **Step 3: 구현**

Create `src/haley/dry_run.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from haley.domain import OrderSide, OrderType


@dataclass(frozen=True)
class DryRunValidationResult:
    valid: bool
    reasons: list[str]
    would_call_real_order_api: bool = False


class DryRunOrderValidator:
    def __init__(self, min_quote_amount: Decimal = Decimal("5000")) -> None:
        self._min_quote_amount = min_quote_amount

    def validate(
        self,
        market: str,
        side: OrderSide,
        order_type: OrderType,
        quote_amount: Decimal | None,
        volume: Decimal | None,
        limit_price: Decimal | None,
    ) -> DryRunValidationResult:
        reasons: list[str] = []
        if not market.startswith("KRW-"):
            reasons.append("KRW_MARKET_REQUIRED")
        if side is not OrderSide.BID and side is not OrderSide.ASK:
            reasons.append("UNSUPPORTED_SIDE")
        if order_type is OrderType.LIMIT and limit_price is None:
            reasons.append("LIMIT_PRICE_REQUIRED")
        if quote_amount is None or quote_amount < self._min_quote_amount:
            reasons.append("MIN_QUOTE_AMOUNT")
        if volume is None or volume <= 0:
            reasons.append("VOLUME_REQUIRED")
        return DryRunValidationResult(
            valid=not reasons,
            reasons=reasons,
            would_call_real_order_api=False,
        )
```

- [ ] **Step 4: API 연결**

Modify `/api/dry-run/order` in `src/haley/api/server.py`:

```python
validator = DryRunOrderValidator()
result = validator.validate(
    market=body.market,
    side=body.side,
    order_type=body.order_type,
    quote_amount=None if body.quote_amount is None else Decimal(body.quote_amount),
    volume=None if body.volume is None else Decimal(body.volume),
    limit_price=None if body.limit_price is None else Decimal(body.limit_price),
)
```

Return:

```python
"valid": result.valid,
"reasons": result.reasons,
"would_call_real_order_api": result.would_call_real_order_api,
```

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_dry_run.py tests/test_api_server.py::test_dry_run_order_validates_request_without_creating_order -v
```

Expected:

```text
All selected tests pass
```

### Task 3.2: LIVE 주문 경로 명시 잠금 테스트

- [ ] **Step 1: 설정값과 실제 주문 차단 테스트 작성**

Add to `tests/test_api_server.py`:

```python
def test_live_trading_remains_locked_in_first_release() -> None:
    store = StateStore.in_memory()
    client = TestClient(create_app(store=store))

    settings = client.get("/api/settings").json()["data"]

    assert settings["live_trading_enabled"] is False
    assert settings["paper_allow_real_order_api"] is False
```

Also ensure Safety Gate 1 exists and passes:

```powershell
python -m pytest tests/test_order_gateway.py -v
```

Expected:

```text
RealOrderGateway create_order/cancel_order attempts raise before any HTTP call.
```

- [ ] **Step 2: 명시 잠금 구현 확인**

`ModeState.allows_real_order_api`는 이미 아래 조건이어야 한다.

```python
return self.mode is RuntimeMode.LIVE and self.live_trading_enabled
```

실제 주문 함수가 생기는 Phase를 기다리지 말고, Phase 3에서 `RealOrderGateway` 잠금 테스트를 유지한다.

```python
from decimal import Decimal

from haley.domain import ModeState, OrderSide, OrderType
from haley.order_gateway import RealOrderGateway


def test_real_order_gateway_rejects_when_live_disabled() -> None:
    http = SpyHttpClient()
    gateway = RealOrderGateway(
        base_url="https://api.upbit.com",
        http_client=http,
        mode=ModeState(),
    )

    with pytest.raises(RuntimeError, match="LIVE trading is disabled"):
        gateway.create_order(
            market="KRW-XRP",
            side=OrderSide.BID,
            order_type=OrderType.LIMIT,
            volume=Decimal("10"),
            price=Decimal("500"),
            identifier="client-1",
        )

    assert http.calls == []
```

- [ ] **Step 3: 통과 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_live_trading_remains_locked_in_first_release tests/test_order_gateway.py -v
```

Expected:

```text
PASSED
```

---

## Phase 4: PAPER 리스크 지표와 상태 초기화

**목표:** PAPER에서 잔고 부족, 노출, 일손실을 실제로 차단하고, 리셋을 안전하게 분리한다.

**선행 조건:** Safety Gate 4와 Safety Gate 5를 먼저 완료한다. 이 Phase는 잔고 부족만 처리하는 단계가 아니며, `RiskMetrics` 연결과 원자적 저장 경계가 완료되어야 한다.

**Files:**
- Modify: `src/haley/paper.py`
- Modify: `src/haley/risk.py`
- Modify: `src/haley/paper_runner.py`
- Modify: `src/haley/state_store.py`
- Modify: `src/haley/api/server.py`
- Test: `tests/test_paper_trading.py`
- Test: `tests/test_paper_runner.py`
- Test: `tests/test_api_server.py`

### Task 4.1: PAPER 잔고 부족 차단

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_paper_trading.py`:

```python
def test_paper_reserve_buy_order_rejects_insufficient_cash() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000"))
    store.save_paper_portfolio(portfolio)
    coordinator = OrderCoordinator(store)
    order = coordinator.create_entry_order(
        market="KRW-XRP",
        side=OrderSide.BID,
        order_type=OrderType.LIMIT,
        quote_amount=Decimal("5000"),
        volume=Decimal("10"),
        limit_price=Decimal("500"),
        exchange_identifier=None,
        state_change=StateChangeRequest(
            request_id="req",
            idempotency_key="idem",
            operator_id="tester",
            reason="insufficient cash test",
        ),
    )
    engine = PaperExecutionEngine(
        store=store,
        portfolio=portfolio,
        fee_rate=Decimal("0.0005"),
    )

    with pytest.raises(ValueError, match="insufficient paper cash"):
        engine.reserve_buy_order(order.order_id)
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_paper_trading.py::test_paper_reserve_buy_order_rejects_insufficient_cash -v
```

Expected:

```text
FAIL because cash can become negative
```

- [ ] **Step 3: 구현**

Modify `PaperExecutionEngine.reserve_buy_order()`:

```python
if self._portfolio.cash_krw < reserved:
    raise ValueError("insufficient paper cash")
```

Also apply equivalent check in `buy()` before subtracting cash:

```python
if self._portfolio.cash_krw < quote_amount + fee:
    raise ValueError("insufficient paper cash")
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_paper_trading.py::test_paper_reserve_buy_order_rejects_insufficient_cash -v
```

Expected:

```text
PASSED
```

### Task 4.2: PAPER 전체 실험 리셋 API 추가

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_api_server.py`:

```python
def test_paper_experiment_reset_clears_virtual_trading_state() -> None:
    store = StateStore.in_memory()
    store.save_paper_portfolio(PaperPortfolio(initial_cash_krw=Decimal("1000000")))
    store.upsert_position(
        PositionState(
            market="KRW-XRP",
            volume=Decimal("10"),
            average_entry_price=Decimal("500"),
        )
    )
    client = TestClient(create_app(store=store))

    response = client.post(
        "/api/paper/experiment-reset",
        json={
            "request_id": "req-reset",
            "idempotency_key": "idem-reset",
            "operator_id": "local-user",
            "reason": "start new paper experiment",
        },
    )

    assert response.status_code == 200
    assert store.list_positions() == []
    assert store.list_orders() == []
    assert store.list_risk_blocks() == []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_paper_experiment_reset_clears_virtual_trading_state -v
```

Expected:

```text
FAIL because endpoint and store cleanup helpers do not exist
```

- [ ] **Step 3: Store 메서드 구현**

Add to `src/haley/state_store.py`:

```python
def reset_paper_experiment_state(self, initial_cash_krw: Decimal) -> PaperPortfolio:
    portfolio = PaperPortfolio(initial_cash_krw=initial_cash_krw)
    with self._lock:
        with self._connection:
            self._connection.execute("DELETE FROM fills")
            self._connection.execute("DELETE FROM orders")
            self._connection.execute("DELETE FROM positions")
            self._connection.execute("DELETE FROM stop_protections")
            self._connection.execute("DELETE FROM risk_blocks")
            self._connection.execute("DELETE FROM alerts")
            self._connection.execute("DELETE FROM data_quality_states")
            self._connection.execute("DELETE FROM reconciliation_state")
            self._save_paper_portfolio_unlocked(portfolio)
    return portfolio
```

Note:

- `execution_events`는 append-only 정책 때문에 삭제하지 않는다.
- 새 실험 구분은 Phase 5의 실험 세션 ID로 처리한다.

- [ ] **Step 4: API 구현**

Add to `src/haley/api/server.py`:

```python
@app.post("/api/paper/experiment-reset")
def reset_paper_experiment(body: StateChangeBody) -> dict[str, Any]:
    body.to_state_change()
    portfolio = store.reset_paper_experiment_state(state.paper_initial_cash_krw)
    return ApiResponse.success(
        request_id=body.request_id,
        data={
            "cash_krw": _decimal_text(portfolio.cash_krw),
            "locked_cash_krw": _decimal_text(portfolio.locked_cash_krw),
            "cleared": [
                "orders",
                "fills",
                "positions",
                "stop_protections",
                "risk_blocks",
                "alerts",
                "data_quality_states",
                "reconciliation_state",
            ],
        },
    )
```

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_paper_experiment_reset_clears_virtual_trading_state -v
```

Expected:

```text
PASSED
```

---

## Phase 5: 실험 세션과 전략 저널

**목표:** 페이퍼 실행 결과를 전략 보완에 사용할 수 있도록 실험 단위와 신호 단위 기록을 저장한다.

**선행 조건:** Safety Gate 6의 승격 게이트가 사용할 수 있도록 실험 세션, 신호 저널, 성과 리포트가 같은 `session_id`로 연결되어야 한다.

**Files:**
- Create: `src/haley/experiments.py`
- Modify: `src/haley/state_store.py`
- Modify: `src/haley/paper_runner.py`
- Modify: `src/haley/api/server.py`
- Test: `tests/test_experiments.py`
- Test: `tests/test_paper_runner.py`
- Test: `tests/test_api_server.py`

### Task 5.1: 실험 세션 모델 추가

- [ ] **Step 1: 테스트 작성**

Create `tests/test_experiments.py`:

```python
from decimal import Decimal

from haley.experiments import ExperimentSession
from haley.state_store import StateStore


def test_experiment_session_can_be_saved_and_listed() -> None:
    store = StateStore.in_memory()
    session = ExperimentSession.start(
        strategy_version="UFS-R1.0",
        initial_cash_krw=Decimal("1000000"),
        markets=["KRW-XRP", "KRW-WLD"],
    )

    store.create_experiment_session(session)
    sessions = store.list_experiment_sessions()

    assert sessions[0].session_id == session.session_id
    assert sessions[0].strategy_version == "UFS-R1.0"
    assert sessions[0].markets == ["KRW-XRP", "KRW-WLD"]
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_experiments.py::test_experiment_session_can_be_saved_and_listed -v
```

Expected:

```text
FAIL because haley.experiments does not exist
```

- [ ] **Step 3: 모델 구현**

Create `src/haley/experiments.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True)
class ExperimentSession:
    session_id: str
    strategy_version: str
    initial_cash_krw: Decimal
    markets: list[str]
    started_at: datetime
    stopped_at: datetime | None = None

    @classmethod
    def start(
        cls,
        strategy_version: str,
        initial_cash_krw: Decimal,
        markets: list[str],
    ) -> "ExperimentSession":
        return cls(
            session_id=f"paper_session_{uuid4().hex}",
            strategy_version=strategy_version,
            initial_cash_krw=initial_cash_krw,
            markets=list(markets),
            started_at=datetime.now(UTC),
        )
```

- [ ] **Step 4: Store 구현**

Add schema:

```sql
CREATE TABLE IF NOT EXISTS experiment_sessions (
    session_id TEXT PRIMARY KEY,
    strategy_version TEXT NOT NULL,
    initial_cash_krw TEXT NOT NULL,
    markets_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    stopped_at TEXT
);
```

Add methods:

```python
def create_experiment_session(self, session: ExperimentSession) -> None:
    with self._connection:
        self._connection.execute(
            """
            INSERT INTO experiment_sessions (
                session_id,
                strategy_version,
                initial_cash_krw,
                markets_json,
                started_at,
                stopped_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.strategy_version,
                _decimal_to_text(session.initial_cash_krw),
                json.dumps(session.markets),
                session.started_at.isoformat(),
                None if session.stopped_at is None else session.stopped_at.isoformat(),
            ),
        )
```

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_experiments.py -v
```

Expected:

```text
PASSED
```

### Task 5.2: 전략 신호 저널 저장

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_experiments.py`:

```python
from haley.experiments import SignalJournalEntry


def test_signal_journal_entry_records_signal_and_outcome_fields() -> None:
    store = StateStore.in_memory()
    entry = SignalJournalEntry(
        entry_id="journal-1",
        session_id="session-1",
        market="KRW-XRP",
        strategy="UFS-R1",
        signal_score=90,
        reasons=["BULLISH_FVG", "BULLISH_OB", "BULLISH_TRAP"],
        rejected_reasons=[],
        entry_price=Decimal("500"),
        stop_price=Decimal("450"),
        target1_price=Decimal("550"),
        target2_price=Decimal("600"),
    )

    store.save_signal_journal_entry(entry)
    saved = store.list_signal_journal_entries("session-1")

    assert saved[0].market == "KRW-XRP"
    assert saved[0].signal_score == 90
    assert saved[0].reasons == ["BULLISH_FVG", "BULLISH_OB", "BULLISH_TRAP"]
```

- [ ] **Step 2: 구현**

Add dataclass:

```python
@dataclass(frozen=True)
class SignalJournalEntry:
    entry_id: str
    session_id: str
    market: str
    strategy: str
    signal_score: int
    reasons: list[str]
    rejected_reasons: list[str]
    entry_price: Decimal | None
    stop_price: Decimal | None
    target1_price: Decimal | None
    target2_price: Decimal | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Add Store table:

```sql
CREATE TABLE IF NOT EXISTS signal_journal (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    market TEXT NOT NULL,
    strategy TEXT NOT NULL,
    signal_score INTEGER NOT NULL,
    reasons_json TEXT NOT NULL,
    rejected_reasons_json TEXT NOT NULL,
    entry_price TEXT,
    stop_price TEXT,
    target1_price TEXT,
    target2_price TEXT,
    created_at TEXT NOT NULL
);
```

- [ ] **Step 3: Runner 연결**

When `signal is None`, save rejected journal entry with `rejected_reasons=["NO_SIGNAL"]`.

When a signal exists, save accepted journal entry before `_fill_paper_entry()`.

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_experiments.py tests/test_paper_runner.py -v
```

Expected:

```text
All selected tests pass
```

### Task 5.3: PAPER 성과 리포트 생성

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_experiments.py`:

```python
from haley.experiments import PaperPerformanceReport, build_paper_performance_report


def test_paper_performance_report_summarizes_session_results() -> None:
    report = build_paper_performance_report(
        session_id="session-1",
        realized_pnl_krw=Decimal("12000"),
        fee_krw=Decimal("500"),
        trade_count=10,
        win_count=6,
        loss_count=4,
        max_drawdown_krw=Decimal("3000"),
        average_r=Decimal("0.45"),
        mae_krw=Decimal("2500"),
        mfe_krw=Decimal("7000"),
        signal_count=30,
        blocked_count=3,
    )

    assert report.session_id == "session-1"
    assert report.net_pnl_krw == Decimal("11500")
    assert report.win_rate == Decimal("0.6")
    assert report.signal_count == 30
    assert report.blocked_count == 3
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_experiments.py::test_paper_performance_report_summarizes_session_results -v
```

Expected:

```text
FAIL because PaperPerformanceReport does not exist
```

- [ ] **Step 3: 구현**

Add to `src/haley/experiments.py`:

```python
@dataclass(frozen=True)
class PaperPerformanceReport:
    session_id: str
    realized_pnl_krw: Decimal
    fee_krw: Decimal
    net_pnl_krw: Decimal
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: Decimal
    max_drawdown_krw: Decimal
    average_r: Decimal
    mae_krw: Decimal
    mfe_krw: Decimal
    signal_count: int
    blocked_count: int


def build_paper_performance_report(
    *,
    session_id: str,
    realized_pnl_krw: Decimal,
    fee_krw: Decimal,
    trade_count: int,
    win_count: int,
    loss_count: int,
    max_drawdown_krw: Decimal,
    average_r: Decimal,
    mae_krw: Decimal,
    mfe_krw: Decimal,
    signal_count: int,
    blocked_count: int,
) -> PaperPerformanceReport:
    win_rate = Decimal("0") if trade_count == 0 else Decimal(win_count) / Decimal(trade_count)
    return PaperPerformanceReport(
        session_id=session_id,
        realized_pnl_krw=realized_pnl_krw,
        fee_krw=fee_krw,
        net_pnl_krw=realized_pnl_krw - fee_krw,
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=win_rate,
        max_drawdown_krw=max_drawdown_krw,
        average_r=average_r,
        mae_krw=mae_krw,
        mfe_krw=mfe_krw,
        signal_count=signal_count,
        blocked_count=blocked_count,
    )
```

- [ ] **Step 4: Store/API 연결**

Add `paper_performance_reports` table in `src/haley/state_store.py` and expose the latest report through `/api/paper/performance`.

Required API response fields:

```json
{
  "session_id": "session-1",
  "realized_pnl_krw": "12000",
  "fee_krw": "500",
  "net_pnl_krw": "11500",
  "trade_count": 10,
  "win_rate": "0.6",
  "max_drawdown_krw": "3000",
  "average_r": "0.45",
  "mae_krw": "2500",
  "mfe_krw": "7000",
  "signal_count": 30,
  "blocked_count": 3
}
```

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_experiments.py tests/test_api_server.py -v
```

Expected:

```text
All selected tests pass
```

---

## Phase 6: 운영 콘솔 안전 UX

**목표:** 비개발자가 차단 이유와 다음 행동을 이해하고 위험 작업을 실수로 실행하지 않게 한다.

**Files:**
- Modify: `src/haley/api/server.py`
- Modify: `web/operations-console.html`
- Test: `tests/test_api_server.py`
- Test: `tests/test_operations_console_ui.py`

### Task 6.1: API가 차단 사유 설명과 다음 행동 반환

- [ ] **Step 1: 실패 테스트 작성**

Add to `tests/test_api_server.py`:

```python
def test_risk_blocks_api_returns_operator_guidance() -> None:
    store = StateStore.in_memory()
    store.record_risk_block(
        RiskBlock(
            reason=RiskBlockReason.UNPROTECTED_POSITION,
            market="KRW-XRP",
            detail="An open position has no stop protection.",
        )
    )
    client = TestClient(create_app(store=store))

    item = client.get("/api/risk/blocks").json()["data"][0]

    assert item["explanation"]
    assert item["resolution"]
    assert item["next_action"]
```

- [ ] **Step 2: 구현**

Add helper in `src/haley/api/server.py`:

```python
def _risk_block_guidance(reason: str) -> dict[str, str]:
    guidance = {
        "UNPROTECTED_POSITION": {
            "explanation": "손절 감시가 없는 포지션이 있어 새 진입을 막았습니다.",
            "resolution": "포지션을 보호 상태로 만들거나 새 PAPER 실험을 시작하세요.",
            "next_action": "포지션과 손절가를 확인한 뒤 실험 리셋 또는 수동 정리를 선택하세요.",
        },
        "DATA_STALE": {
            "explanation": "시장 데이터가 오래되어 현재 가격 판단을 신뢰하기 어렵습니다.",
            "resolution": "데이터 수신이 재개될 때까지 기다리거나 수집기를 재시작하세요.",
            "next_action": "데이터 품질 화면에서 마지막 수신 시각을 확인하세요.",
        },
        "KILL_SWITCH_ON": {
            "explanation": "킬스위치가 켜져 있어 신규 주문을 막았습니다.",
            "resolution": "위험 원인을 확인한 뒤 별도 확인 절차로 해제하세요.",
            "next_action": "복구와 리스크 블록이 모두 해소되었는지 확인하세요.",
        },
    }
    return guidance.get(
        reason,
        {
            "explanation": "안전 조건이 충족되지 않아 신규 주문을 막았습니다.",
            "resolution": "관련 상태와 감사 로그를 확인하세요.",
            "next_action": "리스크 블록 상세를 검토하세요.",
        },
    )
```

Merge into risk block response:

```python
**_risk_block_guidance(block.reason.value)
```

- [ ] **Step 3: 통과 확인**

Run:

```powershell
python -m pytest tests/test_api_server.py::test_risk_blocks_api_returns_operator_guidance -v
```

Expected:

```text
PASSED
```

### Task 6.2: 콘솔에 확인 모달과 안내 문구 추가

- [ ] **Step 1: UI 테스트 작성**

Add to `tests/test_operations_console_ui.py`:

```python
def test_console_contains_operator_guidance_and_confirmations() -> None:
    html = Path("web/operations-console.html").read_text(encoding="utf-8")

    assert "confirmAction" in html
    assert "explanation" in html
    assert "resolution" in html
    assert "next_action" in html
    assert "LIVE 전환 조건" in html
```

- [ ] **Step 2: 구현**

Add JavaScript helper:

```javascript
function confirmAction(message) {
  return window.confirm(message);
}
```

Wrap dangerous actions:

```javascript
$("killSwitch").addEventListener("click", async () => {
  if (!confirmAction("킬스위치를 켜면 신규 주문이 즉시 중단됩니다. 계속할까요?")) return;
  await postStateChange("/api/kill-switch/enable", "manual kill switch from console");
  await refresh();
});
```

Render risk guidance:

```javascript
`${escapeHtml(item.explanation)} · ${escapeHtml(item.resolution)} · ${escapeHtml(item.next_action)}`
```

Add visible text section:

```html
<span class="label-caps text-dim">LIVE 전환 조건</span>
```

- [ ] **Step 3: 통과 확인**

Run:

```powershell
python -m pytest tests/test_operations_console_ui.py -v
```

Expected:

```text
PASSED
```

---

## Phase 7: 전략 검증 고도화

**목표:** 전략 결과를 믿을 수 있도록 Zone 상태, 체결 비교, 백테스트-페이퍼 비교를 추가한다.

**안전 기준:** 수익 신호 고도화보다 검증 가능성이 먼저다. `candle_grace_ms`, 신호 사용 가능 시각, 백테스트-페이퍼 재현성 기록이 없으면 전략 고도화 작업을 시작하지 않는다.

**Files:**
- Modify: `src/haley/strategy.py`
- Modify: `src/haley/market_data.py`
- Modify: `src/haley/paper.py`
- Modify: `src/haley/state_store.py`
- Test: `tests/test_strategy.py`
- Test: `tests/test_market_data.py`
- Test: `tests/test_paper_trading.py`

### Task 7.1: Zone 상태 모델 추가

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_strategy.py`:

```python
from haley.strategy import ZoneState, ZoneStatus


def test_invalidated_zone_cannot_create_signal() -> None:
    zone = ZoneState(
        zone_id="zone-1",
        market="KRW-XRP",
        timeframe="5m",
        lower=Decimal("100"),
        upper=Decimal("110"),
        status=ZoneStatus.INVALIDATED,
    )

    assert zone.can_create_signal is False
```

- [ ] **Step 2: 구현**

Add to `src/haley/strategy.py`:

```python
class ZoneStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FILLED = "FILLED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ZoneState:
    zone_id: str
    market: str
    timeframe: str
    lower: Decimal
    upper: Decimal
    status: ZoneStatus

    @property
    def can_create_signal(self) -> bool:
        return self.status is ZoneStatus.ACTIVE
```

- [ ] **Step 3: 통과 확인**

Run:

```powershell
python -m pytest tests/test_strategy.py::test_invalidated_zone_cannot_create_signal -v
```

Expected:

```text
PASSED
```

### Task 7.1A: 캔들 확정 시점과 룩어헤드 방지 기록

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_market_data.py`:

```python
from datetime import UTC, datetime, timedelta

from haley.market_data import CandleUsePolicy


def test_candle_use_policy_waits_for_grace_period() -> None:
    closed_at = datetime(2026, 6, 7, 0, 0, tzinfo=UTC)
    policy = CandleUsePolicy(candle_grace_ms=500)

    early = policy.evaluate(closed_at=closed_at, now=closed_at + timedelta(milliseconds=499))
    ready = policy.evaluate(closed_at=closed_at, now=closed_at + timedelta(milliseconds=500))

    assert early.usable is False
    assert early.signal_eligible_at == closed_at + timedelta(milliseconds=500)
    assert ready.usable is True
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_market_data.py::test_candle_use_policy_waits_for_grace_period -v
```

Expected:

```text
FAIL because CandleUsePolicy does not exist
```

- [ ] **Step 3: 구현**

Add to `src/haley/market_data.py`:

```python
@dataclass(frozen=True)
class CandleUseDecision:
    usable: bool
    signal_eligible_at: datetime


@dataclass(frozen=True)
class CandleUsePolicy:
    candle_grace_ms: int

    def evaluate(self, *, closed_at: datetime, now: datetime) -> CandleUseDecision:
        eligible_at = closed_at + timedelta(milliseconds=self.candle_grace_ms)
        return CandleUseDecision(usable=now >= eligible_at, signal_eligible_at=eligible_at)
```

- [ ] **Step 4: Runner 연결**

`PaperRunner`가 신호 평가 전에 `CandleUsePolicy`를 적용하고, 사용할 수 없는 캔들은 `last_action="WAITING_FOR_CANDLE_GRACE"`로 남긴다.

- [ ] **Step 5: 통과 확인**

Run:

```powershell
python -m pytest tests/test_market_data.py tests/test_paper_runner.py -v
```

Expected:

```text
All selected tests pass
```

### Task 7.2: 페이퍼 체결가 비교 로그 추가

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_paper_trading.py`:

```python
def test_paper_fill_records_reference_price_gap() -> None:
    store = StateStore.in_memory()
    portfolio = PaperPortfolio(initial_cash_krw=Decimal("1000000"))
    engine = PaperExecutionEngine(
        store=store,
        portfolio=portfolio,
        fee_rate=Decimal("0"),
    )

    gap = engine.calculate_reference_price_gap(
        paper_fill_price=Decimal("101"),
        reference_price=Decimal("100"),
    )

    assert gap == Decimal("0.01")
```

- [ ] **Step 2: 구현**

Add method:

```python
def calculate_reference_price_gap(
    self,
    paper_fill_price: Decimal,
    reference_price: Decimal,
) -> Decimal:
    if reference_price <= 0:
        raise ValueError("reference_price must be positive")
    return (paper_fill_price - reference_price) / reference_price
```

- [ ] **Step 3: 통과 확인**

Run:

```powershell
python -m pytest tests/test_paper_trading.py::test_paper_fill_records_reference_price_gap -v
```

Expected:

```text
PASSED
```

### Task 7.3: 백테스트-페이퍼 신호 재현성 비교

- [ ] **Step 1: 테스트 작성**

Add to `tests/test_strategy.py`:

```python
from haley.strategy import SignalReplayComparison


def test_signal_replay_comparison_finds_missing_paper_signal() -> None:
    comparison = SignalReplayComparison.compare(
        backtest_signal_ids=["KRW-XRP:2026-06-07T00:00:00"],
        paper_signal_ids=[],
    )

    assert comparison.matched_count == 0
    assert comparison.missing_in_paper == ["KRW-XRP:2026-06-07T00:00:00"]
    assert comparison.extra_in_paper == []
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest tests/test_strategy.py::test_signal_replay_comparison_finds_missing_paper_signal -v
```

Expected:

```text
FAIL because SignalReplayComparison does not exist
```

- [ ] **Step 3: 구현**

Add to `src/haley/strategy.py`:

```python
@dataclass(frozen=True)
class SignalReplayComparison:
    matched_count: int
    missing_in_paper: list[str]
    extra_in_paper: list[str]

    @classmethod
    def compare(
        cls,
        *,
        backtest_signal_ids: list[str],
        paper_signal_ids: list[str],
    ) -> "SignalReplayComparison":
        backtest = set(backtest_signal_ids)
        paper = set(paper_signal_ids)
        return cls(
            matched_count=len(backtest & paper),
            missing_in_paper=sorted(backtest - paper),
            extra_in_paper=sorted(paper - backtest),
        )
```

- [ ] **Step 4: 통과 확인**

Run:

```powershell
python -m pytest tests/test_strategy.py -v
```

Expected:

```text
All strategy tests pass
```

---

## 최종 검증 체크리스트

모든 Phase 완료 후 아래를 실행한다.

```powershell
python -m pytest
python -m compileall src tests
```

예상 결과:

```text
pytest: all tests pass
compileall: exit code 0
```

운영 확인:

```powershell
.\run.bat
```

브라우저:

```text
http://127.0.0.1:8000/console
```

확인 항목:

- 킬스위치 ON 후 다음 tick부터 신규 주문이 차단된다.
- 복구 실행 결과가 `MATCHED`, `MISMATCHED`, `FAILED` 중 하나로 끝난다.
- DRY_RUN이 잘못된 주문을 `valid=false`로 표시한다.
- PAPER 실험 리셋이 포지션과 리스크 블록을 정리한다.
- 실험 세션과 신호 저널이 저장된다.
- 콘솔에서 차단 사유의 쉬운 설명과 다음 행동이 보인다.
- `LIVE_TRADING_ENABLED=false`에서 실제 주문 API 호출은 0건이다.

## 실행 순서 권장

가장 먼저 실행할 묶음:

```text
Phase 1 -> Phase 2 -> Phase 3
```

이유:

- Phase 1은 실행 중 신규 주문 차단의 핵심이다.
- Phase 2는 재시작과 불일치 상황을 안전하게 다룬다.
- Phase 3은 실제 거래 전환의 첫 번째 게이트다.

그 다음:

```text
Phase 4 -> Phase 5 -> Phase 6 -> Phase 7
```

이 순서로 진행하면 안전 기반을 먼저 닫고, 이후 실험 기록과 전략 개선을 안정적으로 붙일 수 있다.
