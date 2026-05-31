# Phase P08: 복구와 대조 확장

## 목적

재시작 또는 장애 이후 `RECOVERY_ONLY` 상태에서 잔고, 미체결 주문, 주문 상세, 포지션을 대조하고 재개 가능성을 판정한다.

## 현재 상태

진행 중:

- `src/haley/recovery.py`에 `RecoveryManager` 골격 추가.
- 잔고 조회 단계 테스트 통과.
- 미체결 주문 조회 단계 테스트 통과.
- 주문 상세 대조 단계 테스트 통과.
- 로컬에 없는 거래소 주문을 mismatch로 기록하는 테스트 통과.
- 잔고 조회 실패 시 민감값이 detail에 남지 않는 테스트 통과.
- `ReconciliationState.RUNNING`, `FAILED` 저장 테스트 통과.

## 남은 작업

- 포지션 재계산.
- 거래소 상태 우선 불일치 기록.
- 재개 가능성 판정.
- API의 `/api/recovery/runs/{recovery_run_id}`와 실제 `RecoveryManager` 연결.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-08-recovery-and-reconciliation.md`를 읽고, 미체결 주문 조회와 주문 상세 대조 테스트부터 작성한 뒤 `RecoveryManager`를 확장해.
