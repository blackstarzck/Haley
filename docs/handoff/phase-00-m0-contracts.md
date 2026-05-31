# Phase P00: M0 계약 마무리

## 목적

구현 전 반드시 고정해야 하는 도메인 모델, 상태 전이, DB 제약, API 공통 계약을 확정한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/development_spec.md`
- `docs/upbit_api_and_trading_system.md`

## 현재 상태

완료:

- `src/haley/domain.py`에 운영 모드, 주문 의도, 주문 상태, 체결, 포지션, 실행 이벤트, 리스크/데이터 품질 모델이 추가됨.
- `src/haley/state_store.py`에 SQLite 기반 주문 저장과 실행 이벤트 저장이 추가됨.
- `src/haley/api_contracts.py`에 API 공통 성공/오류 응답과 상태 변경 요청 계약이 추가됨.
- `src/haley/security.py`에 민감값 마스킹 규칙이 추가됨.
- `tests/test_domain_contracts.py`, `tests/test_state_store.py`, `tests/test_api_contracts.py`, `tests/test_sensitive_data.py`가 추가됨.
- `ExecutionEvent`는 SQLite trigger로 update/delete가 차단됨.
- `OrderState.version` 충돌 방지 테스트가 추가됨.

## 남은 작업

- P00 기준 남은 작업 없음.
- 저장소 확장은 P01에서 계속한다.

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
- 민감값 마스킹 모듈

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

P00은 완료되었다. 다음 세션에서는 `docs/handoff/phase-01-state-store-and-audit.md`를 읽고 저장소 확장과 감사 로그를 테스트 먼저 작성한 뒤 구현해.
