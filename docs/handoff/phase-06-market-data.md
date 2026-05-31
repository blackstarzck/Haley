# Phase P06: 데이터 수집과 데이터 품질

## 목적

Upbit REST/WebSocket 기반으로 시장 데이터를 수집하고, stale/mismatch/market warning 상태를 신규 주문 차단 근거로 제공한다.

## 기준 문서

- `docs/development_plan.md`
- `docs/feature_specification.md`
- `docs/upbit_api_and_trading_system.md`

## 시작 조건

- P05 완료 또는 최소한 API 없이도 데이터 품질 상태를 저장/조회할 수 있는 기반 완료.
- `PAPER`에서 실제 주문 API 호출이 차단됨.

## 현재 상태

진행 중:

- `src/haley/market_data.py`에 `Candle`, `CandleStore`, `DataQualityMonitor`가 추가됨.
- 동일 `market + timeframe + candle_time` 캔들 upsert 테스트 통과.
- synthetic candle이 지표에는 사용 가능하지만 패턴 생성에는 제외되는 테스트 통과.
- stale 감지 테스트 통과.
- REST/WebSocket 가격 불일치 감지 테스트 통과.
- Upbit 공개 WebSocket 구독 payload 생성 테스트 통과.
- KRW 거래대금 상위 알트 선정 테스트 통과.
- 기본값에서 BTC/ETH 제외 테스트 통과.
- market warning/caution을 데이터 품질 차단으로 변환하는 테스트 통과.

## 남은 작업

- 실제 Upbit REST 클라이언트.
- 실제 WebSocket 수집기.
- market warning/caution REST 조회 연결.
- 수집 데이터를 `StateStore`와 API로 연결.
- 재연결과 REST 보정.

## 추가 진행 상태

- `src/haley/upbit.py`에 Upbit REST 클라이언트 추가.
- 공개 `/v1/market/all`, `/v1/ticker/all` 조회 테스트 통과.
- 인증 `/v1/accounts` 잔고 조회 JWT 헤더 생성 테스트 통과.
- Secret/JWT/nonce/query_hash 비노출 테스트 통과.
- Upbit candle WebSocket 메시지 파서 테스트 통과.
- 주입 가능한 `MarketDataCollector.collect_candles` 테스트 통과.

## 작업 범위

- Upbit 공개 REST 클라이언트.
- Upbit WebSocket 수집기.
- ticker, trade, orderbook, candle 수신.
- candle upsert.
- synthetic candle 플래그.
- candle grace 적용.
- stale 감지.
- REST/WebSocket 불일치 감지.
- market warning/caution 조회.

## 제외 범위

- 실제 주문 API.
- 전략 신호 생성.
- 외부 뉴스/김치프리미엄 hard block.

## 완료 조건

- 동일 캔들 upsert 테스트 통과.
- synthetic candle이 FVG/OB/Trap 후보에 쓰이지 않도록 상태가 구분됨.
- stale 상태에서 신규 주문 차단 테스트 통과.
- REST/WebSocket mismatch 상태에서 신규 주문 차단 테스트 통과.
- market warning/caution 상태가 RiskBlock으로 연결되는 테스트 통과.

## 검증 명령

```powershell
python -m pytest
python -m compileall src tests
```

## 다음 세션 시작 지시문

`docs/handoff/phase-06-market-data.md`를 읽고, 캔들 upsert와 stale 감지 테스트부터 작성한 뒤 데이터 수집 기반을 구현해.
