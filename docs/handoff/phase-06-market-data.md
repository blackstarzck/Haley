# Phase P06: 데이터 수집과 데이터 품질

## 목적

업비트 공개 REST/WebSocket 기반으로 시장 데이터를 읽고, stale/mismatch/market warning 상태를 신규 주문 차단 근거로 제공한다.

1차 릴리스에서는 실시간 장시간 데몬보다 PAPER runner가 안전하게 읽고 차단할 수 있는 최소 데이터 품질 기반을 우선한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/upbit_api_and_trading_system.md`

## 시작 조건

- P05 완료 또는 API 없이도 데이터 품질 상태를 저장/조회할 수 있는 기반 완료.
- `PAPER`에서 실제 주문 API 호출이 차단됨.

## 현재 상태

완료:

- `src/haley/market_data.py`에 `Candle`, `CandleStore`, `DataQualityMonitor`, `MarketDataCollector` 추가.
- 같은 `market + timeframe + candle_time` 캔들 upsert 구현.
- synthetic candle은 EMA/ATR 같은 지표에는 사용할 수 있지만 FVG/OB/Trap 패턴 생성에는 제외.
- stale 데이터 감지.
- REST/WebSocket 가격 불일치 감지.
- ticker/trade/orderbook/candle별 마지막 수신 시각 추적.
- Upbit 공개 WebSocket subscription payload 생성.
- Upbit candle WebSocket 메시지 파싱.
- Upbit REST minute candle 파싱.
- KRW 거래대금 상위 알트 마켓 선택. 기본값은 BTC/ETH 제외.
- market warning/caution payload를 데이터 품질 차단 상태로 변환.
- `CandleUsePolicy`로 캔들 마감 후 grace period 전 신호 평가 차단.
- `PaperRunner`가 신호 평가 전에 캔들 grace period를 확인하고 `WAITING_FOR_CANDLE_GRACE` 상태를 남김.
- `src/haley/upbit.py`에 공개 `/v1/market/all`, `/v1/ticker/all`, `/v1/candles/minutes/{unit}` 조회 클라이언트 추가.
- 인증이 필요한 `/v1/accounts`, `/v1/orders/open`, `/v1/order`은 읽기 전용 복구/대조 조회에만 사용.

## 검증된 안전 조건

| 조건 | 증거 |
|---|---|
| 같은 캔들은 append가 아니라 upsert된다 | `tests/test_market_data.py::test_candle_store_upserts_same_market_timeframe_and_time` |
| synthetic candle은 패턴 생성에 쓰이지 않는다 | `tests/test_market_data.py::test_synthetic_candle_can_feed_indicators_but_not_patterns`, `tests/test_strategy.py::test_ufs_r1_signal_engine_does_not_use_synthetic_for_patterns` |
| stale 상태는 신규 진입을 차단한다 | `tests/test_risk_manager.py`, `tests/test_paper_runner.py::test_paper_runner_tick_records_risk_block_before_order_creation` |
| REST/WebSocket mismatch는 데이터 품질 차단 상태가 된다 | `tests/test_market_data.py::test_data_quality_monitor_detects_stale_and_price_mismatch`, `tests/test_domain_contracts.py::test_data_quality_state_blocks_when_stale_or_mismatched` |
| market warning/caution은 신규 진입 차단 상태가 된다 | `tests/test_market_data.py::test_market_event_warning_or_caution_blocks_new_entry` |
| 캔들 grace period 전에는 신호 평가와 주문이 진행되지 않는다 | `tests/test_market_data.py::test_candle_use_policy_waits_for_grace_period`, `tests/test_paper_runner.py::test_paper_runner_waits_for_candle_grace_before_signal_evaluation` |
| 공개 ticker와 candle 조회는 인증 헤더 없이 동작한다 | `tests/test_upbit_client.py`, `tests/test_paper_runner.py::test_paper_runner_fetches_public_rest_candles_before_signal_evaluation` |

## 남은 후속 작업

아래 항목은 1차 PAPER MVP 이후 확장이다.

- 장시간 WebSocket 데몬.
- 자동 재연결과 backoff.
- REST 기반 자동 캔들 보정 루프.
- market warning/caution REST 조회 주기화.
- orderbook gap의 실시간 감지.
- 데이터 품질 상태의 만료/해소 정책 고도화.

## 제외

- 실제 주문 API.
- 전략 파라미터 최적화.
- 외부 뉴스/김치프리미엄 hard block 기본 적용.

## 검증 명령

```powershell
python -m pytest tests/test_market_data.py tests/test_upbit_client.py tests/test_paper_runner.py -v
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```

## 다음 세션 시작 지시문

`docs/handoff/phase-06-market-data.md`와 `docs/handoff/release-01-paper-mvp-scope.md`를 읽고, 데이터 수집은 신규 주문 안전성의 입력으로만 확장한다. 실제 주문 API는 별도 승인 전까지 구현하거나 호출하지 않는다.
