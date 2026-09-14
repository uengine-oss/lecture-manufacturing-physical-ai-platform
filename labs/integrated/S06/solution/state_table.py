"""S06 · 거부·실패·재조회 상태표 (정답본).

각 상황이 끝났을 때 사건 상태(event.status), 실행 기록 수(action_log 행 수), 거부 코드를 적는다.
검사는 hydops/b8_action/service.py 의 실제 함수를 메모리 저장소로 돌린 결과와 비교한다.
"""

STATE_TABLE = {
    # 에이전트 제안이 검사를 통과한 직후 — 사람 승인 전
    "proposed":            {"status": "PENDING_APPROVAL", "action_logs": 0, "error": None},
    # 승인 거부 버튼
    "rejected":            {"status": "REJECTED",         "action_logs": 0, "error": None},
    # 승인 후 부하 감소 명령 성공 직후 (재측정 대기)
    "approved_executed":   {"status": "VERIFYING",        "action_logs": 1, "error": None},
    # 재측정 창에서 55°C 이하 10초 연속
    "recovered":           {"status": "CLOSED",           "action_logs": 1, "error": None},
    # 심각한 저하: 명령은 성공했지만 재측정 미개선
    "not_improved":        {"status": "ESCALATED",        "action_logs": 1, "error": None},
    # 다음 명령 실패 주입 후 승인
    "command_failed":      {"status": "ESCALATED",        "action_logs": 1, "error": None},
    # 승인값 0.4 (허용 범위 0.6~1.0 이탈)
    "out_of_range":        {"status": "ESCALATED",        "action_logs": 0, "error": "VALUE_OUT_OF_RANGE"},
    # 승인 기록 없이 실행 요청 (approved=True 주장만 있음)
    "no_approval_record":  {"status": "PENDING_APPROVAL", "action_logs": 0, "error": "APPROVAL_NOT_FOUND"},
    # 실행 뒤 같은 사건에 승인 버튼을 한 번 더
    "duplicate_decision":  {"status": "VERIFYING",        "action_logs": 1, "error": "NOT_WAITING_FOR_APPROVAL"},
    # 첫 재측정 창의 유효 관측이 70% 미만 → 다음 창을 기다린다 (재조회)
    "insufficient_first":  {"status": "VERIFY_HOLD",      "action_logs": 1, "error": None},
    # 다음 창에서 다시 재측정 → 회복
    "insufficient_then_recovered": {"status": "CLOSED",   "action_logs": 1, "error": None},
}
