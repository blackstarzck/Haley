# 이미지 개념 정리와 팩트 체크

작성일: 2026-05-26
분리 기준: upbit_auto_trading_strategy_spec.md의 관련 장을 목적별 문서로 분리


> 원본 문서에서 분리된 상세 문서입니다. 허브 문서: `../../upbit_auto_trading_strategy_spec.md`

## 1. 이미지별 내용 정리

### 1.1 `step-01.png` - 오더블럭(Order Block)

핵심 주장:

- 오더블럭은 강한 가격 변동 직전에 형성된 특정 가격 범위다.
- 스마트 머니 또는 큰 주문의 흔적으로 해석한다.
- 상승형 오더블럭은 강한 상승 전 마지막 하락 캔들 구간, 하락형 오더블럭은 강한 하락 전 마지막 상승 캔들 구간으로 설명된다.
- 형성 원리는 유동성 확보, 스탑 헌팅, 반대 매매 유도, 이후 본래 방향 재개로 설명된다.
- 진입은 유동성 sweep, 구조 형성, 갭(FVG), 오더블럭 재방문을 함께 볼수록 신뢰도가 높다고 설명한다.
- 손절은 오더블럭을 만든 캔들의 꼬리 고점/저점 또는 몸통 기준으로 제시한다.
- 익절은 고점/저점 돌파, 구조 돌파, 반대 오더블럭, 반대 구조 출현으로 제시한다.

자동화 관점:

- "스마트 머니" 자체는 업비트 데이터로 직접 관측 불가능하다.
- 하지만 "마지막 반대색 캔들 + 강한 변동 + 구조 돌파 + 재방문"은 OHLCV로 수치화 가능하다.
- 업비트 현물 기준 하락형 오더블럭은 숏 진입이 아니라 보유 자산 청산, 신규 매수 금지, 리스크 축소 신호로만 사용한다.

### 1.2 `step-02.png` - FVG(Fair Value Gap)

핵심 주장:

- FVG는 3개 캔들 구조에서 급격한 이동으로 남은 불균형 구간이다.
- 상승형 FVG는 1번 캔들 고가와 3번 캔들 저가 사이 빈 공간, 하락형 FVG는 1번 캔들 저가와 3번 캔들 고가 사이 빈 공간으로 설명된다.
- FVG는 가격이 되돌아와 채우려는 성향이 있으며, 오더블럭과 함께 쓰면 좋은 진입 근거라고 설명한다.
- 진입은 FVG 재방문, 유동성 sweep, 오더블럭과 겹침, 충분한 갭 크기 조건을 함께 사용하라고 제시한다.
- 손절은 FVG 형성 캔들의 꼬리, 저점/고점, 리스크 허용범위 기준으로 제시한다.
- 익절은 FVG를 만든 파동의 고점/저점, 구조 돌파, 반대 FVG 또는 반대 구조 출현으로 제시한다.

자동화 관점:

- FVG는 3캔들 규칙으로 가장 명확하게 자동화 가능하다.
- 다만 업비트는 연속 거래 시장이므로 주식의 실제 공백 갭과 다르게, 캔들 집계 단위에서 생기는 "범위 미거래"로 해석해야 한다.
- 갭 크기가 너무 작으면 수수료/슬리피지에 묻히므로 ATR 또는 가격 대비 최소 폭 필터가 필요하다.

### 1.3 `step-03.png` - 추세선(Trend Line)

핵심 주장:

- 추세선은 시장 방향성을 시각화하는 도구다.
- 상승 추세선은 의미 있는 저점들을 연결하고, 하락 추세선은 의미 있는 고점들을 연결한다.
- 추세선은 가격을 움직이는 원인이 아니라 시장 참여자의 심리와 유동성이 모이는 구간으로 설명된다.
- 진입 전략은 추세선 반등(Bounce)과 추세선 이탈 후 리테스트(Breakout & Retest)로 나뉜다.
- Q&A에서는 몸통이 아니라 꼬리(wick)를 기준으로 선을 긋는다고 설명한다.

자동화 관점:

- 임의로 선을 긋는 방식은 구현 불가에 가깝다.
- 자동매매에서는 피벗 고점/저점 기반 선형 회귀, RANSAC, 또는 최근 N개 피벗 연결 규칙으로 고정해야 한다.
- "각도"와 "터치 횟수"는 ATR 대비 거리 오차와 최소 피벗 수로 수치화한다.

### 1.4 `step-04.png` - 채널(Channel)

핵심 주장:

- 채널은 두 추세선을 평행하게 배치한 가격 변동 범위다.
- 상승 채널, 하락 채널, 횡보 채널, 확장 채널이 제시된다.
- 채널 상단은 저항, 하단은 지지로 사용한다.
- 전략은 채널 하단 매수/상단 익절, 채널 이탈 후 리테스트 진입, 과도한 이탈 후 복귀, 함정 패턴 회피 등이다.

자동화 관점:

- 회귀 채널로 구현 가능하다.
- 수동 평행선 대신 최근 N개 캔들의 선형 회귀 중심선과 표준편차/ATR 폭을 사용하면 안정적이다.
- 채널 매매는 추세 구간과 횡보 구간을 구분하지 않으면 잦은 손절이 발생할 수 있다.

### 1.5 `step-05.png` - Fake out과 함정(Trap)

핵심 주장:

- Fake out은 지지/저항/추세선/채널 등을 일시 돌파한 뒤 원래 범위로 복귀하는 움직임이다.
- Trap은 돌파를 믿고 진입한 참여자들이 반대 방향 움직임에 갇히는 구조다.
- 유동성 sweep, 지지/저항 레벨, 차트 패턴, 이동평균선 등을 함께 보라고 설명한다.
- 진입은 돌파 실패 후 재진입, 리테스트 실패, 원래 구간 복귀를 기준으로 제시된다.
- 손절은 fake out 저점/고점 바깥, 익절은 반대 유동성 구간 또는 1R/2R로 제시된다.

자동화 관점:

- 가장 구현 가치가 높은 부분이다.
- "이전 피벗 고점/저점 돌파 후 N캔들 내 종가 복귀"로 정의할 수 있다.
- 현물 기준으로 하락 fake out은 롱 진입 후보가 될 수 있고, 상승 fake out은 보유 물량 청산 또는 매수 금지 신호가 된다.

## 2. 이미지에서 추출한 매매 개념/전략 목록

| 개념 | 자동화 가능성 | 업비트 데이터 | 사용 방식 |
|---|---:|---|---|
| 오더블럭 | 중간 | OHLCV, 거래량, 체결 | 진입 후보 구역 |
| FVG | 높음 | OHLCV | 불균형 구간 및 되돌림 구역 |
| 추세선 | 중간 | OHLCV | 방향 필터, 반등/이탈 조건 |
| 채널 | 높음 | OHLCV | 평균 회귀/돌파 필터 |
| Fake out / Trap | 높음 | OHLCV, 체결, 호가 | 핵심 진입 트리거 |
| 유동성 Sweep | 중간 | OHLCV, 체결, 호가 | 이전 고점/저점 돌파 후 복귀 |
| 스탑 헌팅 | 낮음 | 직접 관측 불가 | 유동성 sweep으로 대체 |
| 스마트 머니 매집/분산 | 낮음 | 직접 관측 불가 | 거래량/체결강도/호가 불균형으로 대체 |
| 구조 돌파(BOS) | 높음 | OHLCV | 피벗 고점/저점 돌파 |
| 리테스트 | 높음 | OHLCV | 돌파 레벨 재접근 후 반응 |

## 3. 각 전략의 논리 구조 분석

### 3.1 오더블럭 논리

이미지 논리:

1. 큰손이 반대 방향으로 가격을 흔들어 유동성을 만든다.
2. 마지막 반대색 캔들 구간에 큰 주문 흔적이 남는다.
3. 이후 강한 변동과 구조 돌파가 발생한다.
4. 가격이 해당 구간으로 되돌아오면 재진입 기회가 된다.

자동화 규칙:

- 상승형 OB 후보:
  - 최근 `lookback_ob` 캔들 안에서 마지막 음봉을 찾는다.
  - 그 다음 `displacement_window` 캔들 안에 다음 조건이 발생해야 한다.
  - 종가가 최근 피벗 고점을 돌파한다.
  - 상승 캔들 몸통 크기가 `ATR * impulse_atr_mult` 이상이다.
  - 거래량이 `volume_sma * volume_mult` 이상이다.
  - 같은 구간에 상승형 FVG가 있으면 신뢰도 가산.
- 하락형 OB 후보:
  - 현물 자동매매에서는 신규 숏 진입이 아니라 청산/회피 구간으로 사용한다.

취약점:

- "기관 주문"은 직접 확인할 수 없다.
- OB는 사후적으로 잘 보이는 경우가 많아 과최적화 위험이 높다.

### 3.2 FVG 논리

자동화 규칙:

- 상승형 FVG:
  - `low[i] > high[i-2]`
  - 구간: `[high[i-2], low[i]]`
  - 중간 캔들 몸통 또는 전체 range가 `ATR * impulse_atr_mult` 이상이면 유효.
- 하락형 FVG:
  - `high[i] < low[i-2]`
  - 구간: `[high[i], low[i-2]]`
- 최소 폭:
  - `(zone_high - zone_low) / close[i] >= min_gap_pct`
  - 또는 `zone_width >= ATR * min_gap_atr`

거래 사용:

- 상승형 FVG가 상승 OB와 겹치고, 가격이 FVG 50% 이상 되돌림 후 반등하면 롱 후보.
- 하락형 FVG는 보유 포지션 청산 또는 신규 매수 금지 필터.

### 3.3 추세선 논리

자동화 규칙:

- 피벗 저점: `low[i]`가 좌우 `pivot_left/right`개 캔들의 저점보다 낮다.
- 피벗 고점: `high[i]`가 좌우 `pivot_left/right`개 캔들의 고점보다 높다.
- 상승 추세선:
  - 최근 피벗 저점 2~5개를 연결하거나 회귀한다.
  - 기울기 `slope > min_slope`.
  - 터치 횟수 `touch_count >= 2`.
  - 각 터치의 거리 `abs(low - line_price) <= ATR * line_tolerance_atr`.
- 하락 추세선:
  - 현물 기준으로 매수 금지/청산 필터에 우선 사용한다.

거래 사용:

- 추세선 반등은 단독 진입 금지.
- FVG/OB/Trap 중 최소 1개 이상과 결합해야 한다.

### 3.4 채널 논리

자동화 규칙:

- 최근 `channel_window`개 종가에 대해 선형 회귀 중심선을 계산한다.
- 채널 폭은 잔차 표준편차 `k * stdev` 또는 `ATR * channel_atr_mult`로 둔다.
- 상단/하단 접촉은 `distance_to_band <= ATR * tolerance`.
- 채널 유형:
  - 상승 채널: 회귀 기울기 양수.
  - 하락 채널: 회귀 기울기 음수.
  - 횡보 채널: 기울기 절댓값 작고 ADX 또는 추세강도 낮음.

거래 사용:

- 상승 채널 하단 + bullish trap + 상승 FVG/OB 겹침: 롱 후보.
- 채널 상단 접근 + 상승 fake out: 익절 또는 비중 축소.
- 하락 채널 안에서는 신규 롱 진입을 제한한다.

### 3.5 Fake out / Trap 논리

자동화 규칙:

- 하방 fake out, 롱 후보:
  - 최근 피벗 저점 또는 지지 레벨 아래로 `break_threshold` 이상 이탈.
  - `reclaim_window` 캔들 안에 종가가 다시 레벨 위로 복귀.
  - 복귀 캔들의 거래량이 평균 이상.
  - 아래꼬리 비율이 `lower_wick / range >= wick_ratio_min`.
  - 선택적으로 호가 불균형이 매수 우위로 전환.
- 상방 fake out, 청산/회피 후보:
  - 최근 피벗 고점 또는 저항 레벨 위로 돌파.
  - `reclaim_window` 캔들 안에 종가가 다시 레벨 아래로 복귀.
  - 위꼬리 비율이 기준 이상.

### 3.6 공통 Zone 상태 모델

OB, FVG, 지지/저항, 채널 밴드, 추세선 레벨은 모두 `Zone`으로 통합 관리한다. 단순히 "유효/무효"만 저장하지 않고, 생성 이후 수명주기를 상태로 관리한다.

```text
created -> active -> touched -> partially_filled -> mitigated -> filled
                                      \-> invalidated
                                      \-> expired
```

상태 정의:

- `created`: 확정 캔들 기준으로 구역이 처음 생성된 상태.
- `active`: 아직 진입 근거로 사용할 수 있는 상태.
- `touched`: 가격이 구역에 1회 이상 닿은 상태.
- `partially_filled`: FVG/OB 구역 일부가 채워진 상태.
- `mitigated`: FVG 50% 이상 또는 OB 중심값 이상 되돌림이 발생한 상태.
- `filled`: FVG가 완전히 채워졌거나 OB 구역을 완전히 관통한 상태.
- `invalidated`: 종가가 구역 반대편으로 확정 이탈한 상태.
- `expired`: 생성 후 `zone_max_age_candles`를 초과한 상태.

진입 후보는 `active`, `touched`, 첫 번째 `mitigated` 상태까지만 허용한다. `filled`, `invalidated`, `expired` 상태는 점수 가산에도 사용하지 않는다.

Zone 경계 계산은 전략 파라미터로 고정한다.

```text
zone_boundary_mode = wick | body | hybrid
```

- `wick`: 꼬리 전체를 포함해 넓게 잡는다.
- `body`: 몸통 기준으로 좁게 잡는다.
- `hybrid`: 진입 구역은 몸통, 무효화/손절은 꼬리 기준으로 둔다.

FVG는 "채워지면 진입"이 아니라 "채워지는 상태를 관찰한 뒤 반응을 확인"하는 구조로 쓴다. `touch`, `50% fill`, `full fill`, `close-through fill`을 구분하고, 완전 채움 이후에는 같은 FVG를 신규 진입 근거로 재사용하지 않는다.

Fake out / Trap은 레벨을 분리한다.

- `sweep_level`: 가격이 일시적으로 이탈한 기준 레벨.
- `reclaim_level`: 종가가 복귀해야 하는 기준 레벨.
- `entry_trigger_level`: 실제 진입을 허용하는 확인 레벨.
- `invalidation_level`: 진입 아이디어가 무효화되는 레벨.

Trap 확정은 기준 레벨 이탈, `reclaim_window` 안의 종가 복귀, 반대 방향 `min_follow_through_atr` 이상 진행 또는 반응 캔들/거래량/호가 조건 중 최소 2개 확인을 요구한다.

## 4. Bright Data MCP 조사 및 팩트 체크

Bright Data MCP는 로컬 래퍼 `C:\Users\buche\.codex\brightdata-mcp.cmd`로 실행해 `search_engine` 도구를 호출했다. 확인된 MCP 상태:

- `INITIALIZE_OK=true`
- `TOOLS_COUNT=17`
- `search_engine` 실제 호출 성공

조사 쿼리:

- `Upbit API websocket candle trade orderbook official documentation`
- `Upbit API rate limits quotation exchange official documentation`
- `Upbit API create order minimum order amount official documentation`
- `fair value gap order block trading strategy empirical evidence technical analysis`

확인된 공식/보조 자료:

- Upbit Developer Center: https://global-docs.upbit.com/
- Upbit API overview: https://global-docs.upbit.com/reference/api-overview
- Upbit Developer Center guide: https://global-docs.upbit.com/docs/developer-center-overview
- Upbit KR documentation: https://docs.upbit.com/kr
- Upbit official client examples: https://github.com/upbit-exchange/client
- FVG 개념 설명 예시: https://trendspider.com/learning-center/fair-value-gap-trading-strategy/

팩트 체크 결과:

| 항목 | 판단 | 근거/비고 |
|---|---|---|
| 업비트에서 실시간 체결/호가/티커 수신 가능 | 가능 | 공식 WebSocket은 ticker, trade, orderbook 등 실시간 스트림을 제공한다. |
| 업비트에서 캔들 데이터 조회 가능 | 가능 | 공식 Quotation REST API에서 분/일/주/월 캔들 조회를 제공한다. |
| 업비트 WebSocket 캔들 사용 가능 | 가능 | 공식 문서에 WebSocket candle reference가 존재한다. 단, 구현 시 실제 응답 필드와 갱신 주기 테스트 필요. |
| 주문/잔고 자동화 가능 | 가능 | Exchange API는 주문, 주문 조회, 잔고 조회를 제공하며 인증이 필요하다. |
| 오더블럭으로 기관 주문을 확정 가능 | 불가능 | 업비트 공개 데이터만으로 특정 기관/세력 주문을 식별할 수 없다. |
| FVG를 3캔들 가격 불균형으로 검출 | 가능 | OHLCV만으로 계산 가능하다. |
| 추세선/채널을 수동 방식 그대로 구현 | 부적합 | 수동 작도는 주관적이다. 피벗/회귀 기반 규칙으로 바꿔야 한다. |
| Fake out/Trap 자동 검출 | 가능 | 이전 고점/저점 돌파 후 종가 복귀, 꼬리 비율, 거래량 조건으로 수치화 가능하다. |
| 이미지 전략이 장기적으로 수익 보장 | 불가 | 공개 기술적 분석 패턴은 시장/기간/비용에 따라 성과가 크게 달라진다. 반드시 백테스트와 실거래 전 모의 검증 필요. |

