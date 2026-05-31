# Phase P02: OrderCoordinator와 중복 주문 차단

## 목적

신호나 수동 요청을 실제 주문 의도(`OrderIntent`)로 바꾸고, 주문 안전성 규칙에 따라 신규 진입 가능 여부를 판단한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/upbit_api_and_trading_system.md`

## 시작 조건

- P01 완료됨.
- 주문, 이벤트, 감사 로그 저장 기반이 테스트로 검증됨.

## 현재 상태

완료:

- `src/haley/orders.py`에 `OrderCoordinator`가 추가됨.
- `client_order_key` 생성 규칙이 추가됨.
- 주문 요청 해시 생성이 추가됨.
- 주문 제출 전 `OrderIntent` 저장이 추가됨.
- 같은 마켓에 `SUBMITTING`, `UNKNOWN`, `PARTIALLY_FILLED` 주문이 있으면 신규 진입을 차단함.
- timeout을 `UNKNOWN` 상태로 기록하는 메서드가 추가됨.
- `client_order_key`와 업비트 `exchange_identifier` 분리 테스트가 추가됨.

## 작업 범위

- `src/haley/orders.py` 추가.
- `client_order_key` 생성 규칙 구현.
- 주문 요청 해시 생성.
- 주문 제출 전 `OrderIntent` 저장.
- 같은 마켓에 `UNKNOWN`, `SUBMITTING`, `PARTIALLY_FILLED` 주문이 있으면 신규 진입 차단.
- timeout 또는 응답 유실 시 `UNKNOWN` 저장.
- 상태 전이와 이벤트 기록을 하나의 트랜잭션으로 처리.

## 제외 범위

- 실제 Upbit 주문 API 호출.
- PAPER 체결 처리.
- 전략 신호 생성.

## 완료 조건

- 동일 마켓 미확정 주문 차단 테스트 통과.
- timeout 발생 시 `UNKNOWN` 저장 테스트 통과.
- `client_order_key`와 `exchange_identifier`를 같은 값으로 취급하지 않는 테스트 통과.
- 잘못된 상태 전이가 이벤트를 남기지 않는 테스트 통과.
- `python -m pytest` 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

P02는 완료되었다. 다음 세션에서는 `docs/handoff/phase-03-risk-manager.md`를 읽고 P03의 남은 리스크 항목을 테스트 먼저 작성한 뒤 구현해.
