# UFS-R1 전략 명세

작성일: 2026-05-26
분리 기준: upbit_auto_trading_strategy_spec.md의 관련 장을 목적별 문서로 분리


> 원본 문서에서 분리된 상세 문서입니다. 허브 문서: `../../upbit_auto_trading_strategy_spec.md`

## 6. 최종 전략: UFS-R1

전략명: `UFS-R1`  
의미: Upbit FVG-Sweep Reversion v1  
방향: 현물 롱 전용, 하락 신호는 청산/회피  
주요 타임프레임: 5분봉  
보조 타임프레임: 15분봉 추세 필터, 1분봉 진입 세밀화

### 6.1 전략 개요

이미지의 핵심을 다음 구조로 재해석한다.

1. 큰 변동이 발생해 FVG와 OB 후보가 생긴다.
2. 가격이 해당 구간으로 되돌아온다.
3. 되돌림 과정에서 이전 저점 아래를 살짝 이탈했다가 다시 회복하는 하방 fake out이 발생한다.
4. 복귀 캔들에서 거래량/체결/호가가 매수 우위로 바뀐다.
5. 제한된 리스크로 롱 진입한다.
6. 목표는 1R/2R, 이전 고점, 채널 상단, 반대 fake out 중 먼저 도달한 조건이다.

### 6.2 시장 필터

거래 대상:

- KRW 현금 기준 현물 마켓만 사용한다.
- 초기 기본 거래 대상은 KRW 마켓 중 최근 24시간 거래대금 상위 알트 10개다.
- 초기 기본값에서는 BTC/ETH 같은 메이저 마켓은 제외한다. 추후 설정에서 `include_major_markets=true`로 바꿀 수 있다.
- 스프레드가 `max_spread_pct` 이하.
- 최근 24시간 거래대금이 `min_daily_value` 이상.
- 비정상 급등락, 거래 정지, API 오류 종목 제외.
- `GET /v1/market/all?is_details=true` 기준 `market_event.warning == true` 또는 `market_event.caution`에 하나 이상의 경보가 있으면 신규 진입 금지.
- 상장폐지, 거래지원 종료, 유의종목 지정, 투자유의/주의/경고/위험 공지가 확인된 종목은 즉시 위험 자산 목록에 올리고 신규 매수 금지.
- 보유 중인 종목이 위험 자산 목록에 들어가면 자동 물타기와 추가 매수는 금지하고, 유동성/스프레드가 허용 범위일 때 단계적 청산 또는 전량 청산 규칙을 실행한다.
- 특정 종목의 입출금 중단, 네트워크 장애, 체결량 급감, 호가 공백 확대가 감지되면 신규 진입 금지.

추세 필터:

- 15분봉 기준 `EMA20 > EMA60`이면 롱 허용.
- 또는 회귀 채널 기울기 `slope > min_slope`.
- 15분봉이 하락 채널이고 가격이 중심선 아래면 신규 롱 금지.

변동성 필터:

- `ATR(14) / close`가 너무 낮으면 진입 금지.
- `ATR(14) / close`가 너무 높으면 포지션 크기 축소.
- 1분봉 기준 단일 캔들 변동률이 `flash_move_pct` 이상이면 모든 신규 진입을 `cooldown_minutes` 동안 중단.
- 호가 상위 5단계 기준 예상 시장가 슬리피지가 `max_expected_slippage_pct`를 넘으면 시장가 주문 금지.

외부 이벤트 필터:

- 김치프리미엄은 국내 KRW 가격과 해외 기준 가격을 원화 환산해 계산한다. 예: `kimchi_premium = upbit_krw_price / (global_usd_price * usdkrw_rate) - 1`.
- `kimchi_premium_abs >= max_kimchi_premium_abs` 또는 30분 변화폭이 `kimchi_premium_change_limit`을 넘으면 신규 진입 금지 또는 포지션 크기 50% 이상 축소.
- 신뢰 가능한 뉴스/공지 피드에서 해킹, 거래소 장애, 규제, 소송, 상장폐지, 대규모 락업 해제, 스테이블코인 디페깅 같은 이벤트가 감지되면 해당 종목과 연관 종목을 `news_risk_cooldown_minutes` 동안 신규 진입 금지.
- `UPBIT_ONLY` 모드에서는 외부 가격, 환율, 뉴스 데이터를 hard block으로 사용하지 않는다.
- 외부 데이터 실패가 `unknown`일 때의 동작은 5.5의 운영 모드 표를 따른다. `EXTERNAL_REQUIRED`에서만 외부 데이터 실패를 신규 진입 차단 사유로 처리한다.
- 초기 구현에서는 `UPBIT_ONLY`만 사용한다. 김치프리미엄, 해외 가격, 환율, 뉴스 피드는 화면과 설정 구조를 열어둘 수 있지만 hard block으로 적용하지 않는다.

### 6.3 셋업 조건

#### 조건 A: 상승형 FVG

5분봉 기준:

```text
bullish_fvg if low[i] > high[i-2]
fvg_low = high[i-2]
fvg_high = low[i]
fvg_mid = (fvg_low + fvg_high) / 2
```

유효 조건:

```text
(fvg_high - fvg_low) / close[i] >= 0.0015
body[i-1] >= ATR(14)[i-1] * 0.8
volume[i-1] >= SMA(volume, 20)[i-1] * 1.3
```

#### 조건 B: 상승형 OB 후보

```text
최근 impulse 이전 마지막 음봉 candle j
ob_low = low[j]
ob_high = open[j] 또는 high[j]
```

유효 조건:

```text
close[i] > previous_swing_high
impulse_range >= ATR(14) * 1.2
FVG가 OB 가격대와 30% 이상 겹침
```

#### 조건 C: 하방 Fake out / Trap

```text
support = recent_swing_low 또는 OB/FVG 하단
break_low = low[k] < support * (1 - break_threshold)
reclaim = close[k 또는 k+1..k+n] > support
```

유효 조건:

```text
lower_wick_ratio >= 0.45
volume[k] >= SMA(volume, 20) * 1.2
reclaim_window <= 3 candles
```

선택 조건:

```text
orderbook_imbalance = bid_size_top5 / (bid_size_top5 + ask_size_top5)
orderbook_imbalance >= 0.55
```

### 6.4 진입 규칙

진입 판단은 `Hard Block -> Data Quality -> Pattern Expectancy -> Risk Sizing -> Execution` 순서로 수행한다. 점수가 아무리 높아도 hard block이 하나라도 켜져 있으면 주문하지 않는다.

```text
hard_block_pass == true
data_quality_pass == true
trap_confirmed == true
zone_not_invalidated == true
risk_reward_to_target >= 1.5
validated_pattern_expectancy_pass == true
```

`signal_score`는 후보 정렬과 설명용으로 사용한다. `BACKTEST`와 `PAPER` 단계에서는 `signal_score >= threshold` 조건을 실험할 수 있지만, `LIVE` 진입 기준으로 승격하려면 각 점수 항목의 비용 차감 기대값과 워크포워드 검증 근거가 먼저 있어야 한다.

Hard block 조건:

- 유의종목, 상장폐지, 거래지원 종료, 주의/경고/위험 경보.
- 일 손실 제한, 연속 손절 제한, 최대 노출 제한 초과.
- 잔고/미체결/체결 동기화 실패.
- WebSocket/REST 데이터 불일치, stale 데이터, 캔들 보정 실패.
- 레이트 리밋 차단, 인증 실패, 주문 권한 오류.
- `EXTERNAL_RISK_FILTER_ENABLED=true`인 상태에서 김치프리미엄/뉴스/외부 데이터 필터가 `blocked` 또는 `unknown`.
- circuit breaker, kill switch, recovery-only 모드.

가산 조건:

- 유효 FVG 존재.
- 유효 OB 존재.
- FVG와 OB overlap 30% 이상.
- 추세 필터 통과.
- 채널 하단 또는 유효 지지 구간 반응.
- 거래량 impulse.
- 호가 불균형 우호적. 단, 단독 진입 근거로는 사용하지 않는다.

진입 가격:

- 기본: fake out 회복 캔들의 종가 다음 시장가 또는 지정가.
- 보수형: 회복 캔들 고가 돌파 지정가.
- 공격형은 사용하지 않는다.

주문 방식:

- 백테스트: 다음 캔들 시가 체결 가정 + 슬리피지.
- 실거래: 지정가 우선, 미체결 `entry_timeout_sec` 초과 시 취소. 시장가 주문은 예상 슬리피지, 호가 잔량, 일 손실 한도, API 상태가 모두 정상일 때만 제한적으로 허용한다.
- 시장가 주문은 신호 강도 때문에 허용하지 않는다. 신규 진입 시장가는 엄격한 유동성 조건을 통과할 때만 제한적으로 허용하고, 긴급 청산 시장가는 위험 감소 목적일 때만 허용한다.

### 6.5 손절 규칙

초기 손절:

```text
stop = min(fakeout_low, ob_low, fvg_low) - ATR(14) * 0.1
```

손절 주문 원칙:

- 업비트 현물 기준 손절은 거래소 서버에 항상 보장되는 bracket/OCO 주문이라고 가정하지 않는다. 기본 구현은 봇이 가격을 감시하다가 청산 주문을 내는 client-side stop으로 취급한다.
- 진입 주문이 체결되면 즉시 손절 주문 또는 손절 감시 상태가 생성되어야 한다.
- 손절 감시 상태는 봇/서버/네트워크 장애 시 실행되지 않을 수 있으므로, 열린 포지션에는 watchdog, 장애 알림, 재시작 복구, 수동 긴급 청산 절차가 함께 붙어야 한다.
- 손절 가격이 진입가보다 높거나 같게 계산되거나, `unit_risk <= 0`이면 주문을 내지 않는다.
- 손절 폭이 `min_stop_pct`보다 작으면 수수료/슬리피지에 취약하므로 진입 금지.
- 손절 폭이 `max_stop_pct`보다 크면 포지션 크기를 축소하고, 축소 후 최소 주문 금액 미만이면 진입 금지.
- 급락으로 손절가를 건너뛰면 지정가 고집 금지. `emergency_exit_slippage_pct` 안에서는 시장가 또는 즉시 체결 가능한 가격으로 청산한다.
- `max_unprotected_position_sec` 이상 손절 감시 또는 청산 주문이 없는 포지션이 존재하면 신규 진입을 금지하고 운영자에게 즉시 알린다.

무효화 조건:

- 종가가 OB/FVG 하단 아래에서 마감.
- 회복 후 `max_hold_candles_without_progress` 동안 0.5R 이상 전진하지 못함.
- 상방 fake out 발생.
- 15분봉 추세 필터가 하락 전환.

### 6.6 익절 규칙

부분 익절:

- 1R 도달: 50% 매도, 손절가를 진입가 또는 수수료 포함 손익분기점으로 이동.
- 2R 도달: 30% 추가 매도.
- 잔여 20%는 trailing stop.

목표가 후보:

```text
target_1 = entry + risk * 1
target_2 = entry + risk * 2
target_structure = previous_swing_high
target_channel = regression_channel_upper
```

최종 익절:

- 위 목표 중 가장 가까운 유효 목표부터 순차 적용.
- 상방 fake out 확인 시 잔여 전량 청산.

### 6.7 포지션 관리

리스크:

```text
risk_per_trade = account_equity * 0.005  # 0.5%
max_daily_loss = account_equity * 0.02   # 2%
max_open_positions = 3
max_symbol_exposure = account_equity * 0.25
max_total_crypto_exposure = account_equity * 0.60
max_correlated_exposure = account_equity * 0.35
```

수량:

```text
unit_risk = entry_price - stop_price
raw_position_size_krw = risk_per_trade / (unit_risk / entry_price)
liquidity_cap_krw = orderbook_depth_krw_within_slippage * liquidity_use_limit
remaining_daily_risk = max_daily_loss - realized_daily_loss
position_size_krw = min(raw_position_size_krw, max_symbol_exposure, liquidity_cap_krw, remaining_daily_risk / (unit_risk / entry_price))
```

수량 제한:

- 한 종목 총 노출은 `max_symbol_exposure`를 초과할 수 없다.
- 전체 코인 노출은 `max_total_crypto_exposure`를 초과할 수 없다.
- BTC/ETH와 높은 상관을 보이는 알트 포지션 합계는 `max_correlated_exposure`를 초과할 수 없다.
- 동일 종목 추가 진입은 기존 포지션 손절가가 손익분기점 이상으로 올라간 뒤에만 허용한다.
- 손실 중인 포지션에 대한 물타기는 금지한다.

거래 중단:

- 일 손실 2% 도달.
- 연속 손절 3회.
- API 오류/체결 지연/호가 급변 감지.
- 업비트 응답 실패율 임계치 초과.
- 계정 평가금액이 당일 시작 평가금액 대비 `max_intraday_drawdown` 이상 하락.
- 미체결 주문 취소 실패, 잔고 불일치, 체결 이벤트 누락, WebSocket/REST 가격 괴리 발생.
- 업비트 또는 주요 외부 데이터 소스 장애, 거래소 점검, 네트워크 지연 급증.
- 위험 자산 목록 편입, 상장폐지/거래지원 종료 공지, 유의종목 또는 주의 경보 감지.
- 김치프리미엄/뉴스 리스크 필터가 `blocked` 또는 `unknown` 상태.

거래 재개:

- 중단 사유가 해소되고 `cooldown_minutes`가 지난 뒤에만 수동 승인 또는 보수적 자동 재개를 허용한다.
- 재개 첫 24시간은 `risk_per_trade`를 기본값의 50% 이하로 낮춘다.

