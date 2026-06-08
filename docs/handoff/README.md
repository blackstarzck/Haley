# Handoff 문서 사용법

이 디렉터리는 작업이 중간에 끊겨도 다음 세션에서 이어받을 수 있도록 Phase별 연결 정보를 저장한다.

## 진행 순서

| Phase | 문서 | MVP 상태 | 이후 확장 |
|---:|---|---|---|
| P00 | `phase-00-m0-contracts.md` | 완료 | 없음 |
| P01 | `phase-01-state-store-and-audit.md` | 완료 | 저장소 성능/마이그레이션 개선 |
| P02 | `phase-02-order-coordinator.md` | 완료 | 실제 거래소 주문 어댑터는 1차 제외 |
| P03 | `phase-03-risk-manager.md` | 완료 | 추가 외부 hard block |
| P04 | `phase-04-paper-trading.md` | 완료 | 더 정교한 체결 시뮬레이션 |
| P05 | `phase-05-api-and-console.md` | MVP API/정적 콘솔 완료 | 차트, 상세 화면, Playwright UI 회귀 테스트 |
| P06 | `phase-06-market-data.md` | 데이터 품질 골격 완료 | 장시간 WebSocket 데몬, 자동 재연결, REST 보정 루프 |
| P07 | `phase-07-strategy-and-backtest.md` | 전략/백테스트 골격 완료 | 이벤트 스터디, 워크포워드, 전략 고도화 |
| P08 | `phase-08-recovery-and-reconciliation.md` | 읽기 전용 복구/대조 골격 완료 | 실제 포지션 재계산, 거래소 상태 우선 복구 정책 |
| Release 01 | `release-01-paper-mvp-scope.md` | PAPER MVP 범위 고정 | 고급 UI, 실시간 데몬, 후속 LIVE 승인 게이트 |

## 현재 범위 기준

1차 릴리스는 `PAPER + 운영 콘솔` MVP로 고정한다. 새 기능을 더 추가하기보다 기존 P00~P08 구현을 이 기준에 맞춰 닫힌 루프로 연결하고 검증한다.

- 실제 `LIVE` 주문 생성/취소는 1차 릴리스 제외.
- 업비트 인증 API는 복구/대조에 필요한 읽기 전용 조회만 허용한다. 현재 허용 범위는 계좌, 미체결 주문, 주문 상세 조회다.
- `PAPER`, `DRY_RUN`, `RECOVERY_ONLY`, `KILL_SWITCHED`, `LIVE_TRADING_ENABLED=false` 상태에서 실제 주문/취소 HTTP 호출은 0건이어야 한다.
- MVP에 포함되지 않는 항목은 각 Phase의 `남은 후속 작업`으로 남긴다.
- 범위가 바뀌면 `docs/development_plan.md`의 `1차 PAPER MVP 범위 잠금` 섹션을 먼저 갱신한다.

## 세션 시작 체크리스트

- [ ] `AGENTS.md`를 확인한다.
- [ ] `docs/development_plan.md`의 Phase 실행 순서를 확인한다.
- [ ] 이어받을 Phase의 handoff 문서를 읽는다.
- [ ] `git status --short --branch`로 현재 브랜치와 변경 상태를 확인한다.
- [ ] 기존 사용자 변경을 되돌리지 않는다.
- [ ] 구현이 필요한 경우 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.

## 세션 종료 체크리스트

- [ ] 변경한 파일을 handoff 문서에 기록한다.
- [ ] 실행한 검증 명령과 결과를 기록한다.
- [ ] 남은 작업과 다음 세션 시작 지시문을 갱신한다.
- [ ] 실제 주문 API가 열리지 않았는지 확인한다.

## 최근 검증 기준

```powershell
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```
