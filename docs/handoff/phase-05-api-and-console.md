# Phase P05: API 서버와 운영 콘솔

## 목적

운영자가 터미널 없이 현재 봇 상태, 차단 사유, 주문, 포지션, 데이터 품질, 복구 상태를 확인하고 안전 액션을 수행할 수 있게 한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `DESIGN.md`

## 시작 조건

- P04 완료됨.
- PAPER 가상 주문/체결/포지션이 테스트로 검증됨.

## 현재 상태

진행 중:

- `src/haley/api/server.py`에 FastAPI app factory가 추가됨.
- `/api/status` 테스트 통과.
- `/api/orders` 테스트 통과.
- `/api/positions` 테스트 통과.
- `/api/risk/blocks` 테스트 통과.
- `/api/data-quality` 테스트 통과.
- `/api/alerts` 테스트 통과.
- `/api/audit-events` 테스트 통과.
- `/api/settings` 테스트 통과.
- `/api/kill-switch/enable` 테스트 통과.
- `/api/alerts/{alert_id}/ack` 테스트 통과.
- `/api/recovery/run` 골격 테스트 통과.
- `/api/recovery/runs/{recovery_run_id}` 테스트 통과.
- `/api/dry-run/order` 테스트 통과.
- `/api/paper/reset` 테스트 통과.
- `/api/settings/paper` 테스트 통과.
- `web/operations-console.html` 정적 운영 콘솔 초안 추가.
- 로컬 HTTP 서버로 콘솔 렌더링 확인.
- `/console`에서 FastAPI가 운영 콘솔 HTML을 직접 서빙하는 테스트 통과.

## 남은 작업

- 차트 영역과 데이터 품질 상세 화면.
- 복구 단계별 상세 상태.
- DRY_RUN 주문 요청 원문 상세 표시.
- Playwright 기반 회귀 테스트 자동화.

## 작업 범위

- FastAPI 서버 추가.
- `/api/status`, `/api/orders`, `/api/positions`, `/api/risk/blocks`, `/api/data-quality`, `/api/alerts`, `/api/audit-events`, `/api/settings` 구현.
- 킬스위치 ON API 구현.
- 복구 실행 API 골격 구현.
- PAPER 설정 조회/변경 API 구현.
- 운영 요약 화면.
- 주문/포지션 화면.
- 차단 사유 화면.
- 알림/장애 인박스 화면.

## 제외 범위

- `LIVE` 주문 실행.
- 실거래 위험 설정 변경 화면.
- 외부 알림 채널 연동.

## 완료 조건

- API 응답에 `server_time` 포함.
- 금액/가격/수량은 문자열로 반환.
- 민감 정보가 API 응답에 포함되지 않음.
- 상태 변경 API가 `request_id`, `idempotency_key`, `operator_id`, `reason`을 요구.
- 핵심 화면 Playwright 렌더링 검증 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

프론트엔드가 추가된 뒤:

```powershell
npm test
npm run build
```

## 다음 세션 시작 지시문

`docs/handoff/phase-05-api-and-console.md`를 읽고, `/api/status` 계약 테스트부터 작성한 뒤 FastAPI 서버를 구현해.
