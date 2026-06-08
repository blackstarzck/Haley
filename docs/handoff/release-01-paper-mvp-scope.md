# Release 01 PAPER MVP Scope Handoff

## 목표

1차 릴리스 목표는 실제 실거래 `LIVE`가 아니라 `PAPER + 운영 콘솔`이다.

이 단계의 핵심은 새 기능을 계속 붙이는 것이 아니라, 이미 구현된 P00~P08 조각을 닫힌 루프로 연결하고 검증하는 것이다. 실제 주문 생성/취소 API는 별도 승인 전까지 구현하거나 호출하지 않는다.

## 고정 포함 범위

| Phase | MVP 포함 기준 |
|---:|---|
| P00 | 도메인, API, DB 계약과 주문 상태 전이 계약 |
| P01 | SQLite 상태 저장소, 감사 로그, 알림, 리스크, 데이터 품질 저장 |
| P02 | 주문 의도 생성, 중복 진입 차단, `UNKNOWN` 처리, 실행 이벤트 기록 |
| P03 | 킬스위치, 복구 모드, 데이터 품질, 노출, 보호 없는 포지션 차단 |
| P04 | 실제 주문 API 없는 PAPER 잔고, 체결, 포지션, 수수료, PnL |
| P05 | 운영 상태를 확인하고 제어할 수 있는 최소 API와 정적 콘솔 |
| P06 | 마켓 선택, 캔들 파싱/upsert, stale/mismatch 상태와 리스크 연결 |
| P07 | 전략 후보 검출과 백테스트 골격. 실거래 결정에는 사용하지 않음 |
| P08 | 계좌/미체결/주문 상세 조회 기반의 읽기 전용 복구/대조 골격 |

## 명시적으로 제외

- 실제 `LIVE` 주문 생성/취소
- 선물, 마진, 숏, 레버리지
- 실거래 위험 설정 변경 화면
- 장시간 WebSocket 데몬, 자동 재연결 REST 보정 루프
- 고급 차트, 고급 콘솔 상세 화면, 전체 Playwright UI 회귀 테스트
- 이벤트 스터디, 워크포워드, 전략 파라미터 최적화
- 자동 resume 결정, 실제 포지션 재계산, 거래소 상태 우선 복구 정책 완성

## 현재 검증 기준

| 항목 | 판정 | 주요 증거 |
|---|---|---|
| `PAPER` 모드에서 실제 주문 API 호출 없이 주문/체결/포지션 갱신 | 완료 | `tests/test_paper_runner.py::test_paper_runner_never_calls_real_order_or_cancel_api`, `tests/test_paper_trading.py::test_paper_execution_engine_never_calls_real_order_api` |
| 킬스위치 ON 상태에서 신규 주문 차단 | 완료 | `tests/test_paper_runner.py::test_paper_runner_reads_latest_kill_switch_before_ordering`, `tests/test_risk_manager.py::test_risk_manager_blocks_when_kill_switch_is_enabled` |
| `UNKNOWN`, `SUBMITTING`, `PARTIALLY_FILLED`, `CANCEL_FAILED` 주문이 같은 마켓 신규 진입 차단 | 완료 | `tests/test_order_coordinator.py`, `tests/test_paper_runner.py::test_paper_runner_does_not_order_when_blocking_order_exists_for_market` |
| stale 또는 mismatch 데이터 품질 상태에서 신규 진입 차단 | 완료 | `tests/test_risk_manager.py`, `tests/test_paper_runner.py::test_paper_runner_tick_records_risk_block_before_order_creation` |
| 보호 없는 포지션이 허용 시간을 넘기면 신규 진입 차단 및 알림 생성 | 완료 | `tests/test_risk_manager.py::test_risk_manager_blocks_unprotected_positions`, `tests/test_risk_manager.py::test_risk_manager_creates_alert_for_unprotected_position` |
| 운영 콘솔 API에서 현재 상태, 주문, 포지션, 차단 사유, 알림, 감사 로그 확인 | 완료 | `tests/test_api_server.py`, `tests/test_operations_console_ui.py`, 브라우저 수동 확인: `/console` 렌더 오류 없음 |
| 복구/대조는 읽기 전용으로 동작하며 실제 주문 생성/취소를 호출하지 않음 | 완료 | `tests/test_recovery.py`, `tests/test_upbit_client.py::test_upbit_client_lists_open_orders_with_auth_headers`, `tests/test_upbit_client.py::test_upbit_client_fetches_order_detail_with_read_only_auth` |
| MVP 필수 범위 안에서만 남은 작업 진행 | 유지 | 실제 주문 실행, 실거래 위험 설정 변경, 자동 resume 결정은 제외 상태 유지 |

## 최근 운영 확인

2026-06-08 기준 최신 서버에서 아래를 확인했다.

- `/api/status`: `global_blocks`는 중복 제거된 요약으로 반환된다.
- `/api/settings`: 극소 `Decimal` 잔차는 `paper_locked_cash_krw="0"`으로 표시된다.
- `/api/promotion/status`: `allowed=false`, 실제 주문 API 호출 수 `0`.
- `/console`: `runnerState=STOPPED`, `orderGate=BLOCKED`, `riskState=BLOCKED`, `promotionStatus=BLOCKED`, 브라우저 콘솔 오류 없음.

## 남은 후속 작업

아래는 1차 MVP를 벗어나는 후속 확장이다.

- 장시간 WebSocket 수집 데몬과 자동 재연결.
- REST 기반 자동 캔들 보정 루프.
- 실제 포지션 재계산과 거래소 상태 우선 복구 정책.
- 이벤트 스터디, 워크포워드, 전략 파라미터 최적화.
- 전체 Playwright UI 회귀 테스트와 고급 차트 화면.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```

## 다음 세션 시작 지시문

`docs/development_plan.md`의 `1차 PAPER MVP 범위 잠금`과 이 문서를 먼저 읽는다. 새 기능을 추가하기보다 `PAPER + 운영 콘솔` 닫힌 루프의 회귀 테스트와 운영 확인을 우선한다. 실제 주문 생성/취소 API는 별도 승인 전까지 구현하거나 호출하지 않는다.
