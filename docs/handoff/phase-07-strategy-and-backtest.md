# Phase P07: 전략 검출기와 백테스트

## 목적

안전 기반과 PAPER 운영 루프 위에서 FVG, OB, Trap, EMA/ATR, SignalEngine, BacktestEngine을 구현한다.

전략 신호는 설명과 PAPER 검증을 위한 입력이며, hard block을 대체하지 않는다. 1차 릴리스에서는 전략 신호만으로 실거래 진입을 열지 않는다.

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

완료:

- `src/haley/strategy.py`에 FVG, OB 후보, Trap, 피벗 고점, EMA, ATR, 회귀 채널 구현.
- `SignalDecision`, `StrategySignal`, `TradePlan`으로 신호와 주문 계획 분리.
- hard block과 `signal_score` 분리.
- synthetic candle은 FVG/OB/Trap 생성에 사용하지 않음.
- 피벗 고점은 오른쪽 캔들이 닫힌 뒤에만 확정.
- `BacktestEngine` 비용 모델과 지정가 부분 체결/미체결 시뮬레이션 구현.
- `UfsR1SignalEngine`이 FVG/OB/Trap/ATR을 조합해 `StrategySignal`과 `TradePlan` 생성.
- 15분봉 EMA/회귀 채널 필터로 하락 채널 중심선 아래 신규 롱 차단.
- `ZoneStatus`, `ZoneState`로 invalidated/expired zone이 새 신호를 만들 수 없게 모델링.
- `SignalReplayComparison`으로 백테스트 신호와 PAPER 신호 차이를 비교.
- `PaperExecutionEngine.calculate_reference_price_gap()`으로 PAPER 체결가와 기준가 괴리율 계산.
- `CandleUsePolicy`와 `PaperRunner` 연결로 캔들 grace period 전 신호 평가 차단.
- PAPER Runner가 신호 없음 상태에서는 주문하지 않고, UFS-R1 신호와 RiskManager 통과 후에만 PAPER 주문/체결/포지션을 갱신.
- PAPER 포지션에 손절가, 1R/2R 목표가, trailing stop, 미실현 PnL, 관리 단계 기록.
- 1R 50% 익절, 손익분기 stop 이동, 2R 추가 익절, trailing stop 청산 테스트 통과.
- stop 아래 급락은 PAPER emergency exit로 구분해 청산하고 관리 단계에 기록.

## 검증된 조건

| 조건 | 증거 |
|---|---|
| invalidated zone은 새 신호를 만들 수 없다 | `tests/test_strategy.py::test_invalidated_zone_cannot_create_signal` |
| 백테스트와 PAPER 신호 차이를 비교할 수 있다 | `tests/test_strategy.py::test_signal_replay_comparison_finds_missing_paper_signal` |
| synthetic candle은 패턴 생성에서 제외된다 | `tests/test_strategy.py::test_detect_bullish_fvg_uses_three_candles_and_excludes_synthetic`, `tests/test_strategy.py::test_ufs_r1_signal_engine_does_not_use_synthetic_for_patterns` |
| hard block은 신호 점수와 분리된다 | `tests/test_strategy.py::test_signal_generation_keeps_hard_block_separate_from_score`, `tests/test_paper_runner.py::test_paper_runner_hard_block_overrides_signal_score` |
| 룩어헤드 바이어스를 피한다 | `tests/test_strategy.py::test_find_confirmed_pivot_highs_waits_for_right_candles` |
| 비용과 슬리피지를 Decimal로 계산한다 | `tests/test_strategy.py::test_backtest_engine_applies_fee_and_slippage_costs` |
| 지정가 부분 체결과 미체결 상태를 시뮬레이션한다 | `tests/test_strategy.py::test_backtest_limit_order_partial_fill_tracks_order_status`, `tests/test_strategy.py::test_backtest_limit_order_no_fill_when_price_does_not_cross` |
| PAPER 체결가와 기준가 괴리를 계산한다 | `tests/test_paper_trading.py::test_paper_fill_records_reference_price_gap` |
| 캔들 grace period 전 신호 평가를 기다린다 | `tests/test_market_data.py::test_candle_use_policy_waits_for_grace_period`, `tests/test_paper_runner.py::test_paper_runner_waits_for_candle_grace_before_signal_evaluation` |

## 남은 후속 작업

아래 항목은 1차 PAPER MVP 이후 확장이다.

- BacktestEngine의 취소/재주문/장애 시나리오 확장.
- 이벤트 스터디.
- 워크포워드 검증.
- 더 현실적인 호가 기반 체결 모델.
- 전략 파라미터 최적화.

## 제외 범위

- `signal_score`만으로 실거래 진입.
- 검증 불가능한 “세력 의도”, “기관 주문” 판단.
- LIVE 주문 실행.
- 수익률, 승률, 손익비 보장.

## 검증 명령

```powershell
python -m pytest tests/test_strategy.py tests/test_market_data.py tests/test_paper_trading.py tests/test_paper_runner.py -v
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```

## 다음 세션 시작 지시문

`docs/handoff/phase-07-strategy-and-backtest.md`와 `docs/handoff/release-01-paper-mvp-scope.md`를 읽고, 전략 신호는 PAPER 검증과 설명 목적에만 사용한다. hard block이 있으면 신호 점수와 무관하게 주문하지 않는다. 실제 주문 생성/취소 API는 별도 승인 전까지 구현하거나 호출하지 않는다.
