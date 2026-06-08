# Phase P08: 복구와 대조 확장

## 목적

재시작 또는 장애 이후 `RECOVERY_ONLY` 상태에서 잔고와 미체결 주문을 읽기 전용으로 조회하고, 로컬 상태와 대조한 뒤 사용자 수동 재개 확인이 필요한 상태를 남긴다.

1차 릴리스에서는 복구가 자동으로 거래를 재개하지 않는다. 복구 결과가 `MATCHED`여도 `operator_resume_required=True`로 저장해 신규 진입을 막는다. 여기서 `operator`는 플랫폼 운영자가 아니라 이 개인 PAPER 도구의 사용자 수동 확인을 뜻한다.

## 현재 상태

완료:

- `src/haley/recovery.py`에 `RecoveryManager`와 `RecoveryRun` 모델 추가.
- 잔고 조회 단계 기록.
- 미체결 주문 조회 단계 기록.
- 로컬에 없는 거래소 미체결 주문을 mismatch로 기록.
- 잔고 조회 실패 시 민감값이 detail에 남지 않도록 정리.
- `RecoveryRun.recovery_run_id`, `status`, `reconciliation_status`, `steps` 노출.
- `ReconciliationState.operator_resume_required` 저장.
- `MATCHED` 복구 결과도 사용자 수동 재개 확인 전까지 신규 진입 차단.
- `/api/recovery/run`이 주입된 읽기 전용 exchange로 `RecoveryManager`를 실행.
- `/api/recovery/runs/{recovery_run_id}`가 실행 결과를 조회.
- `UpbitRestClient.list_open_orders()`는 `/v1/orders/open` 조회 전용 API만 사용.
- `UpbitRestClient.get_order_detail()`은 `/v1/order` 주문 상세 조회 전용 API만 사용.

## 검증된 안전 조건

| 조건 | 증거 |
|---|---|
| 복구 실행 ID와 단계 상태가 기록된다 | `tests/test_recovery.py::test_recovery_run_exposes_run_id_and_reconciliation_status` |
| 복구 결과가 `MATCHED`여도 자동 재개하지 않는다 | `tests/test_recovery.py::test_recovery_manager_marks_matched_but_requires_user_resume_when_no_mismatches`, `tests/test_api_server.py::test_recovery_run_api_updates_reconciliation_state_without_auto_resume` |
| 미체결 주문 불일치가 mismatch로 기록된다 | `tests/test_recovery.py::test_recovery_manager_checks_open_orders_and_records_mismatch` |
| 민감정보가 실패 detail에 남지 않는다 | `tests/test_recovery.py::test_recovery_manager_records_failure_without_secret_details` |
| API에서 복구 실행과 조회가 가능하다 | `tests/test_api_server.py::test_recovery_run_api_returns_recovery_run_id`, `tests/test_api_server.py::test_get_recovery_run_returns_run_status` |
| 업비트 연동은 읽기 전용 미체결 조회와 주문 상세 조회만 사용한다 | `tests/test_upbit_client.py::test_upbit_client_lists_open_orders_with_auth_headers`, `tests/test_upbit_client.py::test_upbit_client_fetches_order_detail_with_read_only_auth` |

## 남은 후속 작업

아래 항목은 1차 PAPER MVP 이후 확장이다.

- 실제 거래소 체결/잔고 기반 포지션 재계산.
- 거래소 상태 우선 불일치 해소 정책.
- 취소 실패 주문의 조회 후 재시도 정책.
- 사용자 수동 재개 확인 API와 UI.
- 실제 `LIVE` 전환 전 별도 승인 게이트.

## 제외

- 실제 주문 생성/취소 호출.
- 복구 성공 후 자동 신규 진입 재개.
- 실거래 포지션을 자동으로 수정하거나 청산하는 동작.

## 검증 명령

```powershell
python -m pytest tests/test_recovery.py tests/test_api_server.py tests/test_upbit_client.py -v
python -m pytest
python -m compileall src tests
```

최근 확인 결과:

```text
python -m pytest: 165 passed, 1 warning
python -m compileall src tests: success
```

## 다음 세션 시작 지시문

`docs/handoff/phase-08-recovery-and-reconciliation.md`와 `docs/handoff/release-01-paper-mvp-scope.md`를 읽고, 복구는 읽기 전용과 사용자 수동 재개 확인 원칙을 유지한다. 실제 주문 생성/취소 API는 별도 승인 전까지 구현하거나 호출하지 않는다.
