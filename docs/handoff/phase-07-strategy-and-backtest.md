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

## 현재 상태

진행 중:

- `src/haley/strategy.py`에 FVG, 피벗 고점, 신호 결정 기본 모델이 추가됨.
- EMA 계산 테스트 통과.
- ATR 계산 테스트 통과.
- bullish FVG 검출 테스트 통과.
- synthetic candle이 FVG 생성에 사용되지 않는 테스트 통과.
- 피벗 고점은 오른쪽 캔들이 닫힌 뒤에만 확정되는 테스트 통과.
- hard block과 `signal_score` 분리 테스트 통과.
- BacktestEngine 비용 모델 테스트 통과.
- OB 후보 검출 테스트 통과.
- Fake out/Trap 검출 테스트 통과.
- 회귀 채널 계산 테스트 통과.
- BacktestEngine 지정가 부분 체결/미체결 상태 시뮬레이션 테스트 통과.

## 남은 작업

- 추세 필터와 채널 기반 진입 제한 연결.
- BacktestEngine의 취소/재주문/장애 시나리오 확장.
- 이벤트 스터디.

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
