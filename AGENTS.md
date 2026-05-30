# AGENTS.md

이 파일은 이 프로젝트에서 작업하는 AI 개발 에이전트와 협업자를 위한 빠른 안내서다.  
상세 내용은 `docs/` 문서를 기준으로 확인하고, 이 파일은 길잡이와 체크리스트로 사용한다.

## 기본 응답 원칙

- 항상 한국어로 답변한다.
- 객관적 사실과 논리를 기준으로 답변한다.
- 추측과 확인된 사실을 명확히 구분한다.
- 모르는 내용은 아는 척하지 않고, 확인이 필요한 부분을 분명히 말한다.
- 개발 지식이 적은 사용자도 이해할 수 있도록 쉬운 말로 설명한다.
- 전문 용어는 짧게 풀어서 설명한다.
- 복잡한 내용은 단계별 목록, 표, 체크리스트, Mermaid 다이어그램으로 정리한다.
- 코드 작업 전에는 기존 구조와 문서를 먼저 확인한다.
- 수정은 프로젝트의 기존 방식에 맞춰 최소한으로 한다.
- 작업 후에는 변경 내용, 이유, 확인 결과를 간단히 설명한다.

## 프로젝트 핵심 요약

이 프로젝트는 업비트 KRW 현물 시장에서 `UFS-R1` 전략을 검증하고 운영하기 위한 자동매매 시스템이다.

첫 릴리스 목표는 실제 실거래 `LIVE`가 아니라 **`PAPER + 운영 콘솔`**이다.

중요도는 아래 순서를 따른다.

```text
주문 안전성 > 리스크 차단 > 장애 복구 > 검증 가능성 > 전략 수익 신호
```

실시간 실행 우선순위는 아래 순서를 따른다.

```text
KillSwitch > Recovery > CircuitBreaker > Reconciliation > Risk > DataQuality > Signal > Execution
```

앞 단계에서 차단되면 뒤 단계는 주문을 만들 수 없다.

## 문서 우선순위

개발지시를 받을 때는 아래 순서로 문서를 확인한다.

| 우선순위 | 문서 | 용도 |
|---:|---|---|
| 1 | `docs/feature_specification.md` | 실제 구현해야 할 기능 요구사항 기준 문서 |
| 2 | `docs/development_plan.md` | 기능을 어떤 순서와 구조로 구현할지 정리한 개발 기획 |
| 3 | `docs/development_spec.md` | 전체 개발 목표, 모듈, 데이터 모델, 완료 정의 |
| 4 | `docs/upbit_api_and_trading_system.md` | 업비트 API, 주문 상태, 복구, 실시간 시스템 제약 |
| 5 | `docs/ufs-r1_strategy.md` | UFS-R1 전략 조건, 진입, 손절, 익절, 포지션 관리 |
| 6 | `docs/backtest_and_paper_trading.md` | 백테스트, 페이퍼, DRY_RUN, 소액 실거래 검증 조건 |
| 7 | `docs/risk_controls_and_final_decision.md` | 리스크 취약점, 해결책, 구현 우선순위 |
| 8 | `docs/image_concepts_and_factcheck.md` | 이미지 기반 전략 개념과 자동화 가능성, 팩트 체크 |
| 9 | `DESIGN.md` | 운영 콘솔 UI 시각 스타일 기준 |
| 10 | `README.md` | 프로젝트 소개와 실행 안내 |

## 상황별 빠른 참조

| 작업 상황 | 먼저 볼 문서 |
|---|---|
| 개발지시를 해석할 때 | `docs/feature_specification.md`, `docs/development_plan.md` |
| 구현 순서를 정할 때 | `docs/development_plan.md` |
| 기능 누락 여부를 확인할 때 | `docs/feature_specification.md` |
| 운영 모드와 안전 원칙을 확인할 때 | `docs/development_spec.md`, `docs/feature_specification.md` |
| 주문 상태 머신을 구현할 때 | `docs/upbit_api_and_trading_system.md`, `docs/feature_specification.md` |
| `PAPER` 매매를 구현할 때 | `docs/feature_specification.md`, `docs/backtest_and_paper_trading.md` |
| 리스크 차단 로직을 구현할 때 | `docs/feature_specification.md`, `docs/risk_controls_and_final_decision.md` |
| 시장 데이터 수집을 구현할 때 | `docs/upbit_api_and_trading_system.md`, `docs/development_spec.md` |
| FVG/OB/Trap 전략 로직을 구현할 때 | `docs/ufs-r1_strategy.md`, `docs/image_concepts_and_factcheck.md` |
| 백테스트를 구현할 때 | `docs/backtest_and_paper_trading.md` |
| 운영 콘솔 화면을 만들 때 | `docs/feature_specification.md`, `docs/development_plan.md`, `DESIGN.md` |
| API를 만들 때 | `docs/development_plan.md`, `docs/feature_specification.md` |
| 보안과 민감값 처리를 확인할 때 | `docs/development_spec.md`, `docs/upbit_api_and_trading_system.md` |

## 개발 착수 체크리스트

코드 작업을 시작하기 전에 아래를 확인한다.

- [ ] 요청이 어떤 기능 영역인지 확인했다.
- [ ] `docs/feature_specification.md`에서 해당 기능의 요구사항 ID를 확인했다.
- [ ] `docs/development_plan.md`에서 구현 순서와 관련 API/모듈을 확인했다.
- [ ] 기존 파일 구조와 구현 패턴을 확인했다.
- [ ] 실제 주문 API 호출이 필요한 작업인지 확인했다.
- [ ] `PAPER` 또는 `DRY_RUN`에서 실제 주문 호출이 차단되어야 하는지 확인했다.
- [ ] 돈, 수량, 수수료, PnL 계산에 `float`를 쓰지 않는지 확인했다.
- [ ] API Secret, JWT, nonce, query hash가 로그와 응답에 노출되지 않는지 확인했다.
- [ ] 테스트 또는 검증 방법을 정했다.

## 반드시 지켜야 할 구현 원칙

### 운영 모드

- 기본 실행 모드는 `PAPER`다.
- 1차 릴리스에서 `LIVE` 실제 주문 실행은 열지 않는다.
- `PAPER_ALLOW_REAL_ORDER_API=false` 상태에서는 실제 주문 API 호출이 0건이어야 한다.
- 재시작 또는 복구 필요 상태에서는 `RECOVERY_ONLY`로 진입하고 신규 주문을 막는다.
- 킬스위치가 켜져 있으면 신규 주문을 만들지 않는다.

### 주문 안전성

- 주문 전 `OrderIntent`, `client_order_key`, 업비트 `identifier`, 요청 해시를 먼저 저장한다.
- `client_order_key`와 업비트 `identifier`는 같은 값으로 취급하지 않는다.
- 주문 timeout이나 응답 유실은 `UNKNOWN` 상태로 저장한다.
- `UNKNOWN`, `SUBMITTING`, `PARTIALLY_FILLED` 주문이 있으면 같은 마켓 신규 진입을 금지한다.
- 모든 주문 상태 전이는 `ExecutionEvent`로 기록한다.

### 리스크와 손절

- 신호 점수가 높아도 hard block이 있으면 주문하지 않는다.
- 손실 중인 포지션에는 물타기하지 않는다.
- 진입 체결 직후 손절 감시 상태를 만든다.
- `max_unprotected_position_sec`를 넘긴 보호 없는 포지션이 있으면 신규 진입을 막고 알림을 만든다.
- 손절은 거래소 서버에서 항상 보장되는 주문이라고 가정하지 않는다. 기본은 client-side stop이다.

### 데이터 품질

- WebSocket 캔들은 같은 시간 캔들이 여러 번 올 수 있으므로 upsert한다.
- 캔들은 마감 후 `candle_grace_ms`가 지난 뒤 신호에 사용한다.
- `synthetic=true` 캔들은 EMA/ATR 같은 연속 지표에는 사용할 수 있지만 FVG/OB/Trap 생성에는 사용하지 않는다.
- stale 데이터 또는 REST/WebSocket 불일치 상태에서는 신규 진입을 막는다.

### 전략 로직

- `UFS-R1`은 현물 롱 전용 전략이다.
- 하락 신호는 신규 숏이 아니라 청산, 회피, 비중 축소에 사용한다.
- "세력 의도", "기관 주문" 같은 직접 검증 불가능한 개념을 코드 판단값으로 넣지 않는다.
- FVG, OB, Trap, 추세선, 채널은 업비트 데이터로 관측 가능한 규칙으로만 구현한다.
- `signal_score`는 설명과 후보 정렬용이며 hard block을 대체하지 않는다.

## 1차 릴리스 범위

포함:

- 업비트 실시간 데이터 수집
- SQLite 기반 상태 저장
- `PAPER` 가상 KRW 잔고
- 가상 주문, 체결, 포지션, 수수료, PnL
- 주문 상태 머신
- 리스크 매니저
- 킬스위치
- 복구와 대조
- 감사 로그
- 운영 콘솔 API
- 운영 콘솔 화면
- DRY_RUN 주문 요청 검증

제외:

- 실제 `LIVE` 주문 실행
- 선물, 마진, 숏, 레버리지
- 수익률 보장 또는 목표 승률 보장
- 검증 전 `signal_score_threshold`만으로 실거래 진입
- 외부 뉴스/김치프리미엄 hard block 기본 적용
- 손실 포지션 물타기
- 실거래와 직접 연결되는 위험 설정 화면 수정

## 권장 기술 스택

| 영역 | 권장 |
|---|---|
| 백엔드 | Python 3.11+ |
| API 서버 | FastAPI |
| 저장소 | SQLite 우선, 추후 PostgreSQL 가능 |
| 프론트엔드 | Next.js 또는 React |
| 차트 | TradingView Lightweight Charts |
| 스타일 | `DESIGN.md` 기반 다크 운영 대시보드 |
| 테스트 | pytest, Playwright |

## 작업 후 보고 형식

작업을 마친 뒤에는 간단히 보고한다.

- 변경한 파일
- 변경한 이유
- 확인한 테스트 또는 검증 결과
- 남은 주의사항

예시:

```text
변경:
- docs/development_plan.md에 feature_specification.md 참조 추가

이유:
- 개발지시 기준 문서와 구현 계획 문서를 연결하기 위해

확인:
- 문서 상단 참조 목록과 Summary 반영 확인
```
