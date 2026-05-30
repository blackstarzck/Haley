# 업비트 실시간 자동매매 전략 명세서

작성일: 2026-05-26  
분리일: 2026-05-30  
대상 이미지: `step-01.png` ~ `step-05.png`  
전략명: `UFS-R1`  
목표: 이미지에 포함된 코인 매매 개념을 업비트 API에서 제공하는 실시간 데이터만으로 구현 가능한 자동매매 알고리즘으로 재설계한다.

> 주의: 이 문서는 투자 수익, 원금 보전, 특정 승률을 보장하지 않는다. 자동매매에는 수치화 가능한 규칙, 손실 제한, 거래 중단 조건, 검증 절차를 반드시 붙인다. 실제 매매 전에는 손실 가능 금액 안에서만 테스트해야 하며, 본 문서는 투자 권유가 아니라 구현 가능성 검토 자료다.

## 문서 구조

긴 단일 문서를 목적별로 분리했다. 이 파일은 전체 목차와 핵심 의사결정을 담는 허브 문서다.

| 문서 | 역할 | 주요 내용 |
|---|---|---|
| [`docs/image_concepts_and_factcheck.md`](docs/image_concepts_and_factcheck.md) | 리서치와 개념 근거 | 이미지별 OB/FVG/추세선/채널/Trap 정리, 자동화 가능성, Bright Data MCP 팩트 체크 |
| [`docs/ufs-r1_strategy.md`](docs/ufs-r1_strategy.md) | 매매 전략 명세 | UFS-R1 개요, 시장 필터, 셋업, 진입/손절/익절, 포지션 관리 |
| [`docs/upbit_api_and_trading_system.md`](docs/upbit_api_and_trading_system.md) | 시스템/구현 명세 | 업비트 API 데이터, 주문/잔고/레이트 리밋, 운영 모드, 주문 상태 머신, 데이터 구조 |
| [`docs/backtest_and_paper_trading.md`](docs/backtest_and_paper_trading.md) | 검증 계획 | 백테스트, 시간 정합성, 이벤트 스터디, 체결 비용 모델, 페이퍼 트레이딩, 소액 실거래 |
| [`docs/risk_controls_and_final_decision.md`](docs/risk_controls_and_final_decision.md) | 리스크와 최종 판정 | 취약점, 해결 방안, P0/P1/P2 구현 우선순위, 최종 판정 |
| [`docs/development_spec.md`](docs/development_spec.md) | 개발 스펙 | 개발 목표, 시스템 아키텍처, 모듈 명세, 데이터 모델, 마일스톤, 완료 정의 |
| [`upbit_strategy_consensus_report.html`](upbit_strategy_consensus_report.html) | 합의 보고서 | gpt-5.5 별도 에이전트 토론을 반영한 HTML 결론 보고서 |

## 핵심 결론

이미지의 원본 개념을 그대로 자동매매에 넣는 것은 위험하다. 특히 “스마트 머니”, “기관의 발자국”, “세력 의도”는 업비트 공개 API로 직접 검증할 수 없다.

다만 다음 형태로 바꾸면 구현 가능하다.

- FVG: 3캔들 OHLCV 불균형.
- OB: 강한 변동 직전 마지막 반대색 캔들 + 구조 돌파 + 거래량 조건.
- 추세선: 피벗 기반 회귀선.
- 채널: 회귀 채널.
- Fake out/Trap: 이전 피벗 돌파 후 N캔들 내 종가 복귀.
- 유동성: 이전 고점/저점, 거래량, 체결, 호가 불균형으로 대체.

## 구현 우선순위

| 우선순위 | 항목 | 이유 |
|---|---|---|
| P0 | 주문 안전성 | 주문 전 `identifier` 영속 저장, timeout 시 재주문 금지, `UNKNOWN` 주문 신규 진입 차단 |
| P0 | 손절 장애 대응 | 업비트 현물 손절은 기본적으로 client-side stop으로 보고 watchdog과 긴급 청산 절차 필요 |
| P0 | 숫자/주문 정밀도 | 주문/잔고/체결/수수료/PnL은 `Decimal` 또는 정수 최소 단위로 처리 |
| P0 | 리스크 매니저와 킬스위치 | 손절, 포지션 크기, 일 손실, 총 노출, 물타기 금지, 잔고 불일치 차단 |
| P1 | 페이퍼 운영 | 실제 업비트 실시간 데이터와 가상 KRW 현금으로 가상 주문, 체결, 포지션, PnL 검증 |
| P1 | 운영 모드 분리 | 초기값은 `UPBIT_ONLY`, 외부 데이터 모드는 후속 옵션으로 분리 |
| P1 | 검증 단계 분리 | 캔들 검증, 호가 로그 검증, 페이퍼, DRY_RUN, 소액 실거래 순서로 승격 |
| P1 | 시장 이벤트 필터 | 유의종목, 주의 경보, 상장폐지/거래지원 종료, 입출금/거래 장애 차단 |
| P2 | 전략 검출기 | FVG, 피벗/구조 돌파, Fake out/Trap, OB 후보 검출 |
| P2 | 점수화 고도화 | `signal_score_threshold`와 각 가중치는 이벤트 스터디와 워크포워드 검증 뒤 확정 |

## 운영 원칙

```mermaid
flowchart LR
    A[시장 데이터 수집] --> B[Hard Block 확인]
    B --> C[Data Quality 확인]
    C --> D[Pattern Expectancy 검증]
    D --> E[Risk Sizing]
    E --> F[Execution]
    F --> G[Reconciliation]
    G --> H[Audit Log]
```

- 점수는 진입 후보를 설명하고 정렬하는 보조 도구다.
- 실거래 진입은 hard block, 데이터 품질, 손익비, 유동성, 주문 가능성, 검증된 패턴 기대값을 먼저 통과해야 한다.
- 초기 실사용 목표는 `PAPER` 모드다. 실제 업비트 시세를 사용하지만 실제 주문은 내지 않고, 사용자가 설정한 가상 KRW 현금으로 매매 활동을 기록한다.
- 초기 거래 대상은 KRW 마켓 거래대금 상위 알트 10개이며, 기본값에서는 BTC/ETH 같은 메이저 마켓을 제외한다.
- 외부 뉴스/김치프리미엄/환율은 초기 hard block으로 쓰지 않고 `UPBIT_ONLY`로 시작한다.
- 안전장치는 신호 로직보다 우선한다.
- 수익 보장을 전제로 하지 않으며, 실제 투입 전 백테스트와 페이퍼 트레이딩을 통과해야 한다.

## 산출물 관리

- 상세 문서를 수정할 때는 이 허브 문서의 링크와 우선순위도 함께 확인한다.
- 구현 계획을 만들 때는 `docs/risk_controls_and_final_decision.md`의 P0 항목부터 처리한다.
- 전략 성능 개선은 P0/P1 안전장치와 검증 체계가 준비된 뒤 진행한다.
