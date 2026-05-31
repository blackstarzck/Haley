# Haley 문서 허브

업비트 실시간 자동매매 전략 `UFS-R1`의 문서 모음입니다.

이 저장소의 목표는 수익 보장이 아니라, 이미지 기반 매매 개념을 업비트 API로 관측 가능한 규칙으로 바꾸고 안전장치, 검증 절차, 운영 화면을 갖춘 자동매매 시스템으로 설계하는 것입니다.

## 현재 운영 방향

초기 실사용 목표는 `PAPER + 운영 콘솔`입니다.

```text
실제 업비트 실시간 시세
        ↓
UFS-R1 전략 판단
        ↓
가상 KRW 현금으로 가상 매수/매도
        ↓
가상 체결, 포지션, 손절/익절, 손익 기록
```

`PAPER`는 단순 신호 표시가 아니라 가상 돈으로 실제 운영처럼 매매 활동을 검증하는 모드입니다. `DRY_RUN`은 그 다음 단계에서 실제 주문 직전의 요청 형식과 거래소 제약을 확인하는 모드입니다. `LIVE` 실거래는 별도 승인 전까지 범위 밖입니다.

## 기본 결정값

| 항목 | 값 |
|---|---|
| 기본 모드 | `PAPER` |
| 기준 통화 | KRW 현금 |
| 거래 대상 | KRW 마켓 거래대금 상위 알트 10개 |
| 메이저 마켓 | 초기 기본값에서는 BTC/ETH 제외 |
| 외부 데이터 | `UPBIT_ONLY` |
| 실행 환경 | 로컬 PC |
| 알림 | 내부 이벤트/화면은 유지, 외부 채널 연동은 보류 |
| 위험 결정 | 킬스위치, 재개 승인, 긴급 청산은 사용자 수동 |
| 실거래 | `LIVE_TRADING_ENABLED=false` |

## 빠른 시작 문서

처음 읽는다면 아래 순서가 가장 좋습니다.

1. [전체 허브 문서](upbit_auto_trading_strategy_spec.md): 목표, 핵심 결론, 구현 우선순위
2. [개발 기획](docs/development_plan.md): 첫 릴리스 범위, 운영 콘솔, API, 마일스톤
3. [개발 스펙](docs/development_spec.md): 모듈 명세, 파라미터, 완료 정의
4. [UFS-R1 전략 명세](docs/ufs-r1_strategy.md): 시장 필터, 셋업, 진입/손절/익절
5. [업비트 API와 실시간 거래 시스템](docs/upbit_api_and_trading_system.md): 주문, 상태 머신, 데이터 구조
6. [백테스트와 페이퍼 검증 계획](docs/backtest_and_paper_trading.md): 검증 단계와 합격 기준
7. [리스크 통제와 최종 판정](docs/risk_controls_and_final_decision.md): 취약점과 안전 우선순위

## 실행

Windows에서 아래 한 줄만 실행하면 로컬 운영 콘솔이 열린다.

```bat
.\run.bat
```

브라우저에서 아래 주소를 연다.

```text
http://127.0.0.1:8000/console
```

종료는 실행 중인 터미널에서 `Ctrl + C`를 누른다.

PowerShell 실행 정책을 직접 우회해서 실행하려면 아래 명령을 사용할 수도 있다.

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

## 설정 파일

- [.env.example](.env.example): 공개 가능한 예시 설정
- `.env.local`: 로컬 개인 설정 파일, Git에 올리지 않음

`PAPER` 테스트의 핵심 설정은 아래와 같습니다.

```env
HALEY_MODE=PAPER
PAPER_INITIAL_CASH_KRW=1000000
PAPER_VIRTUAL_TRADING_ENABLED=true
PAPER_ALLOW_REAL_ORDER_API=false
LIVE_TRADING_ENABLED=false
```

## 핵심 원칙

- 안전장치는 신호 로직보다 우선합니다.
- `PAPER`에서도 주문, 체결, 잔고, 수수료, PnL은 실제 돈처럼 `Decimal` 또는 정수 최소 단위로 계산합니다.
- 업비트 현물 손절은 서버 보장 OCO 주문으로 가정하지 않고, 기본적으로 client-side stop으로 취급합니다.
- `signal_score`는 설명과 후보 정렬용이며, 검증 전 실거래 확정 기준으로 쓰지 않습니다.
- API 키는 최소 권한만 사용하고 출금 권한은 절대 넣지 않습니다.
