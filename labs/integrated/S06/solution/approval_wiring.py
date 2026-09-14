"""S06 · 모의 승인 버튼과 부하 감소 도구 연결 (정답본).

- 관제 화면(hydops/b9_dashboard/static/app.js)의 승인·거부 버튼은 POST /api/events/{event_id}/decision 을 부른다.
- 서버(app.py)는 로컬 모드에서 Orchestrator.decide → service.record_decision → (승인이면) service.execute 로 넘긴다.
- 실행 도구(executor.execute_sim_action)는 조치 ID 를 시뮬레이터 메서드에 연결한다.
"""

DECISION_PATH = "/api/events/{event_id}/decision"
BUTTON_TO_DECISION = {"승인": "APPROVED", "거부": "REJECTED"}

# 조치 ID → HydraulicSimulator 메서드 이름
ACTION_TO_METHOD = {"REDUCE_LOAD": "apply_load", "FAN_BOOST": "apply_fan_boost"}


def decision_body(button: str, approver: str, approve_value: float) -> dict:
    decision = BUTTON_TO_DECISION[button]
    # 거부할 때는 값을 보내지 않는다 (app.js decide 와 같다)
    return {"approver": approver, "decision": decision, "value": approve_value if decision == "APPROVED" else None}
