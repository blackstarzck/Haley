# Phase P03: RiskManager 기본 차단

## 목적

주문 생성 전 반드시 통과해야 하는 hard block과 리스크 차단을 한곳에서 판단한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/risk_controls_and_final_decision.md`

## 시작 조건

- P02 완료.
- 주문 의도 생성과 미확정 주문 차단이 테스트로 검증됨.

## 작업 범위

- `src/haley/risk.py` 추가.
- 실행 우선순위 반영: `KillSwitch > Recovery > CircuitBreaker > Reconciliation > Risk > DataQuality > Signal > Execution`.
- 킬스위치 ON 차단.
- 복구 미완료 차단.
- stale 데이터 차단.
- REST/WebSocket 불일치 차단.
- 일 손실 한도 차단.
- 종목별/전체 노출 한도 차단.
- 보호 없는 포지션 차단.
- 차단 사유를 `RiskBlock`과 감사 이벤트로 기록.

## 제외 범위

- 시장 데이터 수집기 구현.
- 실거래 주문.
- 전략 점수 계산.

## 완료 조건

- 각 hard block 조건별 테스트 통과.
- hard block이 있으면 `signal_score`와 무관하게 주문이 생성되지 않는 테스트 통과.
- 보호 없는 포지션이 있으면 신규 진입 차단과 알림 생성 테스트 통과.
- `python -m pytest` 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-03-risk-manager.md`를 읽고, 실행 우선순위와 킬스위치 차단 테스트를 먼저 작성한 뒤 `RiskManager`를 구현해.
