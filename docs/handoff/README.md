# Handoff 문서 사용법

이 디렉터리는 작업이 중간에 끊겨도 다른 세션에서 이어받을 수 있도록 Phase별 인계 정보를 저장한다.

## 진행 순서

| Phase | 문서 | 상태 |
|---:|---|---|
| P00 | `phase-00-m0-contracts.md` | 진행 중 |
| P01 | `phase-01-state-store-and-audit.md` | 대기 |
| P02 | `phase-02-order-coordinator.md` | 대기 |
| P03 | `phase-03-risk-manager.md` | 대기 |
| P04 | `phase-04-paper-trading.md` | 대기 |
| P05 | `phase-05-api-and-console.md` | 대기 |
| P06 | `phase-06-market-data.md` | 대기 |
| P07 | `phase-07-strategy-and-backtest.md` | 대기 |

## 세션 시작 체크리스트

- [ ] `AGENTS.md`를 확인한다.
- [ ] `docs/development_plan.md`의 `Phase Execution Order`를 확인한다.
- [ ] 이어받을 Phase의 handoff 문서를 읽는다.
- [ ] `git status --short --branch`로 현재 브랜치와 변경 상태를 확인한다.
- [ ] 기존 사용자 변경을 되돌리지 않는다.
- [ ] 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.

## 세션 종료 체크리스트

- [ ] 변경한 파일을 handoff 문서에 기록한다.
- [ ] 실행한 검증 명령과 결과를 기록한다.
- [ ] 남은 작업과 다음 세션 시작 지시문을 갱신한다.
- [ ] 실제 주문 API가 열리지 않았는지 확인한다.
