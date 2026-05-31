# Phase P01: 상태 저장소 확장과 감사 로그

## 목적

주문 저장소를 주문 외 핵심 운영 상태까지 확장하고, 감사 로그를 별도 컴포넌트로 분리한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/development_spec.md`

## 시작 조건

- P00 완료됨.
- 도메인 모델과 API 공통 계약 테스트 통과.
- 주문 상태 전이와 `ExecutionEvent` 저장 테스트 통과.
- `ExecutionEvent` update/delete 차단 테스트 통과.

## 현재 상태

완료:

- `AuditLogger`가 추가됨.
- 체결 저장/조회가 추가됨.
- 포지션 upsert/조회가 추가됨.
- 리스크 차단 기록/조회가 추가됨.
- 알림 생성/확인/조회가 추가됨.
- 데이터 품질 상태 저장/조회가 추가됨.
- 대조 상태 저장/조회가 추가됨.
- 감사 로그 payload는 민감값 마스킹 후 저장됨.

## 작업 범위

- `AuditLogger` 추가.
- `fills`, `positions`, `risk_blocks`, `alerts`, `data_quality_states`, `reconciliation_states` 저장 구조 추가.
- 금액, 가격, 수량은 문자열 저장 후 `Decimal`로 복원.
- 민감값은 저장 전 마스킹.
- 저장소 쓰기는 가능한 한 트랜잭션 단위로 처리.

## 제외 범위

- 실제 Upbit API 호출.
- PAPER 체결 로직.
- UI 구현.

## 완료 조건

- 체결 저장과 조회 테스트 통과.
- 포지션 저장과 조회 테스트 통과.
- 리스크 차단 사유 저장과 조회 테스트 통과.
- 알림 저장, 확인, 조회 테스트 통과.
- 감사 로그에 민감값이 저장되지 않는 테스트 통과.
- 데이터 품질 상태 저장/조회 테스트 통과.
- 대조 상태 저장/조회 테스트 통과.
- `python -m pytest` 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

P01은 완료되었다. 다음 세션에서는 `docs/handoff/phase-03-risk-manager.md`를 읽고 P03의 남은 리스크 항목을 테스트 먼저 작성한 뒤 구현해.
