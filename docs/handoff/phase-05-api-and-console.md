# Phase P05: API 서버와 운영 콘솔

## 목적

사용자가 개발 지식 없이도 현재 PAPER 운영 상태, 차단 사유, 주문, 포지션, 데이터 품질, 복구 상태를 확인하고 안전한 운영 액션을 수행할 수 있게 한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `DESIGN.md`

## 시작 조건

- P04 완료.
- PAPER 가상 주문, 체결, 포지션, 수수료, PnL이 테스트로 검증됨.
- 실제 주문 API는 1차 릴리스에서 열지 않음.

## 현재 상태

완료:

- `src/haley/api/server.py`에 FastAPI app factory 구현.
- `/console`에서 `web/operations-console.html` 정적 콘솔 제공.
- `/`는 `/console`로 redirect.
- `/api/status`: 모드, 신규 주문 가능 여부, 킬스위치, 복구 상태 제공.
- `/api/orders`: 주문 계약 제공. 금액/수량은 문자열로 반환.
- `/api/positions`: 포지션, 손절/익절, PnL 문자열 반환.
- `/api/risk/blocks`: 차단 사유와 사용자 안내 문구 제공.
- `/api/data-quality`: stale/mismatch와 피드별 수신 시각 제공.
- `/api/alerts`, `/api/alerts/{alert_id}/ack`: 알림 조회와 확인 처리.
- `/api/audit-events`: 민감정보가 마스킹된 감사 이벤트 제공.
- `/api/settings`, `/api/settings/paper`: PAPER 안전 설정 조회/변경.
- `/api/kill-switch/enable`: 신규 주문 차단 모드 저장.
- `/api/recovery/run`, `/api/recovery/runs/{recovery_run_id}`: 읽기 전용 복구 실행/조회.
- `/api/dry-run/order`: 실제 주문 없이 주문 형식 검증.
- `/api/paper/reset`, `/api/paper/experiment-reset`: PAPER 상태 초기화.
- `/api/paper-runner/status`, `/api/paper-runner/start`, `/api/paper-runner/stop`: PAPER runner 상태와 제어.
- `/api/paper/performance`: PAPER 실험 성과 리포트 조회.
- `/api/promotion/status`: LIVE 전환 조건을 조회하되 실제 LIVE 실행은 열지 않음.
- 운영 콘솔에 runner, PAPER 설정, 킬스위치, 리스크 안내, LIVE 전환 조건 패널 표시.

## 검증된 안전 조건

| 조건 | 증거 |
|---|---|
| 공통 API 응답에 `server_time`, `request_id`가 포함된다 | `tests/test_api_server.py::test_status_api_returns_common_response_shape` |
| 금액/가격/수량이 문자열로 반환된다 | `tests/test_api_server.py::test_positions_api_returns_decimal_values_as_strings`, `tests/test_api_server.py::test_orders_api_returns_order_contract_without_sensitive_values` |
| 민감정보가 API 응답에 노출되지 않는다 | `tests/test_api_server.py::test_audit_events_api_returns_masked_payload`, `tests/test_sensitive_data.py` |
| 상태 변경 API가 `request_id`, `idempotency_key`, `operator_id`, `reason`을 요구한다 | `tests/test_api_server.py::test_kill_switch_enable_requires_state_change_request` |
| `LIVE_TRADING_ENABLED=false`가 유지되고 실제 주문 API가 열리지 않는다 | `tests/test_api_server.py::test_live_trading_remains_locked_in_first_release`, `tests/test_order_gateway.py` |
| DRY_RUN 검증은 주문을 만들지 않는다 | `tests/test_api_server.py::test_dry_run_order_validates_request_without_creating_order` |
| 콘솔 HTML이 API 경로와 핵심 패널을 포함한다 | `tests/test_operations_console_ui.py` |
| 최신 콘솔 렌더링이 오류 없이 동작한다 | 브라우저 수동 확인: `/console`, `runnerState=STOPPED`, `orderGate=BLOCKED`, `promotionStatus=BLOCKED`, 오류 로그 없음 |

## 남은 후속 작업

아래 항목은 1차 PAPER MVP 이후 확장이다.

- 차트 영역 고도화.
- 복구 단계별 상세 화면.
- DRY_RUN 주문 요청 원문 상세 표시.
- 전체 Playwright UI 회귀 테스트 자동화.
- 외부 알림 채널 연동.

## 제외

- 실제 `LIVE` 주문 실행.
- 실거래 위험 설정 변경 화면.
- API 키 입력/저장 화면.
- 실거래 전환 버튼.

## 검증 명령

```powershell
python -m pytest tests/test_api_server.py tests/test_operations_console_ui.py -v
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```

## 다음 세션 시작 지시문

`docs/handoff/phase-05-api-and-console.md`와 `docs/handoff/release-01-paper-mvp-scope.md`를 읽고, 운영 콘솔은 PAPER 상태 관측과 안전 제어에 집중한다. 실제 주문 생성/취소 API, API 키 저장, 실거래 위험 설정 변경은 별도 승인 전까지 구현하지 않는다.
