# Phase P00: M0 계약 마무리

## 목적

구현 전 반드시 고정해야 하는 도메인 모델, 상태 전이, DB 제약, API 공통 계약을 확정한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/development_spec.md`
- `docs/upbit_api_and_trading_system.md`

## 현재 상태

일부 완료:

- `src/haley/domain.py`에 운영 모드, 주문 의도, 주문 상태, 체결, 포지션, 실행 이벤트, 리스크/데이터 품질 모델이 추가됨.
- `src/haley/state_store.py`에 SQLite 기반 주문 저장과 실행 이벤트 저장이 추가됨.
- `tests/test_domain_contracts.py`, `tests/test_state_store.py`가 추가됨.
- 마지막 확인 기준으로 `python -m pytest`는 12개 테스트 통과.

## 남은 작업

- API 공통 성공 응답 형식 정의.
- API 공통 오류 응답 형식 정의.
- 상태 변경 API 공통 입력 모델 정의: `request_id`, `idempotency_key`, `operator_id`, `reason`.
- 민감값 마스킹 규칙 정의.
- DB 스키마 초안 확장 여부 결정.
- `ExecutionEvent` append-only 원칙을 테스트로 강화.
- 문서의 M0 완료 기준과 코드 타입이 일치하는지 점검.

## 완료 조건

- 도메인 모델과 API 계약이 테스트로 고정된다.
- `exchange_identifier` 전역 UNIQUE 제약이 테스트된다.
- 활성 `client_order_key` 중복 방지가 테스트된다.
- `OrderState.version` 충돌 방지 테스트가 있다.
- `ExecutionEvent`가 append-only로만 기록됨을 테스트한다.
- `python -m pytest`가 통과한다.

## 다음 Phase로 넘길 산출물

- 안정화된 `domain.py`
- 안정화된 `state_store.py`
- API 공통 계약 모듈
- M0 계약 테스트

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-00-m0-contracts.md`를 읽고, M0의 API 공통 응답/오류 형식과 상태 변경 입력 모델을 테스트 먼저 작성한 뒤 구현해.
