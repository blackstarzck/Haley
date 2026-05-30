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
