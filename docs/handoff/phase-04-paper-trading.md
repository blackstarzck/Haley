# Phase P04: PAPER 가상 주문과 체결

## 목적

실제 주문 API 호출 없이 실제 운영처럼 가상 KRW 잔고, 주문, 체결, 포지션, 수수료, 손익을 갱신한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/backtest_and_paper_trading.md`

## 시작 조건

- P03 완료.
- 주문 안전성과 기본 리스크 차단이 테스트로 검증됨.

## 작업 범위

- `PaperPortfolio` 추가.
- `PaperExecutionEngine` 추가.
- 가상 KRW 현금과 locked 금액 관리.
- 가상 매수/매도 체결.
- 부분 체결 처리.
- 수수료 계산.
- 평균 진입가, 실현/미실현 PnL 계산.
- 체결 직후 손절 감시 상태 생성.
- `PAPER_ALLOW_REAL_ORDER_API=false`에서 실제 주문 API 호출 0건 보장.

## 제외 범위

- 실시간 Upbit WebSocket 수집.
- 실제 주문 API 호출.
- 전략 신호 검출.

## 완료 조건

- 가상 매수 체결 후 KRW 잔고와 포지션 갱신 테스트 통과.
- 가상 매도 체결 후 실현 PnL 갱신 테스트 통과.
- 수수료가 `Decimal`로 계산되는 테스트 통과.
- 손실 중 포지션 물타기 차단 테스트 통과.
- `PAPER_ALLOW_REAL_ORDER_API=false` 실제 주문 API 호출 차단 테스트 통과.
- `python -m pytest` 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-04-paper-trading.md`를 읽고, 가상 매수 체결 후 잔고와 포지션이 갱신되는 테스트부터 작성한 뒤 PAPER 엔진을 구현해.
