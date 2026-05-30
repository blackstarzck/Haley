# Phase P07: 전략 검출기와 백테스트

## 목적

안전 기반과 PAPER 운영 루프 위에서 FVG, OB, Trap, EMA/ATR, SignalEngine, BacktestEngine을 구현한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/ufs-r1_strategy.md`
- `docs/backtest_and_paper_trading.md`
- `docs/image_concepts_and_factcheck.md`

## 시작 조건

- P06 완료.
- 시장 데이터와 데이터 품질 차단이 테스트로 검증됨.
- PAPER에서 주문/리스크 오류를 관측할 수 있음.

## 작업 범위

- ATR(14), EMA20, EMA60.
- Pivot 확정.
- FVG 검출.
- OB 후보 검출.
- Fake out/Trap 검출.
- Signal과 TradePlan 분리.
- BacktestEngine.
- 비용 모델.
- 이벤트 스터디.

## 제외 범위

- `signal_score`만으로 실거래 진입.
- 검증 불가능한 “세력 의도”, “기관 주문” 판단.
- LIVE 주문 실행.

## 완료 조건

- 미래 캔들을 쓰지 않는 피벗 테스트 통과.
- synthetic candle은 FVG/OB/Trap 생성에 사용하지 않는 테스트 통과.
- hard block이 있으면 신호 점수와 무관하게 주문하지 않는 테스트 통과.
- 백테스트와 페이퍼가 같은 Feature/Signal 로직을 재사용.
- 룩어헤드 바이어스 방지 테스트 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-07-strategy-and-backtest.md`를 읽고, synthetic candle을 제외하는 FVG 테스트와 피벗 확정 테스트부터 작성한 뒤 전략 검출기를 구현해.
