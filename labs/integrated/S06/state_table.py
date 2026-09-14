"""S06 · 거부·실패·재조회 상태표 — 빈칸 ____ 을 채운다.

각 상황이 끝났을 때 사건 상태(event.status), 실행 기록 수(action_log 행 수), 거부 코드를 적는다.
- status 후보: PENDING_APPROVAL, REJECTED, VERIFYING, VERIFY_HOLD, CLOSED, ESCALATED
- error 후보 : None(거부 없음), VALUE_OUT_OF_RANGE, APPROVAL_NOT_FOUND, NOT_WAITING_FOR_APPROVAL
검사는 hydops/b8_action/service.py 의 실제 함수를 메모리 저장소로 돌린 결과와 비교한다.
"""

____ = "____"  # 빈칸 표시 (None 이 정답인 칸도 직접 None 으로 바꾼다)

STATE_TABLE = {
    # 에이전트 제안이 검사를 통과한 직후 — 사람 승인 전
    "proposed":            {"status": "PENDING_APPROVAL", "action_logs": 0, "error": None},  # 예시 (채워 둠)
    # 승인 거부 버튼
    "rejected":            {"status": ____, "action_logs": ____, "error": ____},
    # 승인 후 부하 감소 명령 성공 직후 (재측정 대기)
    "approved_executed":   {"status": ____, "action_logs": ____, "error": ____},
    # 재측정 창에서 55°C 이하 10초 연속
    "recovered":           {"status": ____, "action_logs": ____, "error": ____},
    # 심각한 저하: 명령은 성공했지만 재측정 미개선
    "not_improved":        {"status": ____, "action_logs": ____, "error": ____},
    # 다음 명령 실패 주입 후 승인
    "command_failed":      {"status": ____, "action_logs": ____, "error": ____},
    # 승인값 0.4 (허용 범위 0.6~1.0 이탈)
    "out_of_range":        {"status": ____, "action_logs": ____, "error": ____},
    # 승인 기록 없이 실행 요청 (approved=True 주장만 있음)
    "no_approval_record":  {"status": ____, "action_logs": ____, "error": ____},
    # 실행 뒤 같은 사건에 승인 버튼을 한 번 더
    "duplicate_decision":  {"status": ____, "action_logs": ____, "error": ____},
    # 첫 재측정 창의 유효 관측이 70% 미만 → 다음 창을 기다린다 (재조회)
    "insufficient_first":  {"status": ____, "action_logs": ____, "error": ____},
    # 다음 창에서 다시 재측정 → 회복
    "insufficient_then_recovered": {"status": ____, "action_logs": ____, "error": ____},
}
