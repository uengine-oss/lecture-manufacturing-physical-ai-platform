"""S07 · 조치 도구의 실행 전 정책 검사 (정답본).

원본: lecture/system/hydops/b8_action/executor.py 의 execute_sim_action.
수업용 복사본은 DB·그래프 대신 repo 객체를 주입받는다. 그래서 가짜(fake) 저장소로 단위 테스트할 수 있다.

repo 가 제공해야 하는 함수
- get_event(event_id) -> dict | None           (event 테이블 한 행)
- get_approval(approval_id) -> dict | None     (approval 테이블 한 행 — 사람 승인 태스크가 남긴 기록)
- find_action_log(idem_key) -> dict | None     (같은 멱등 키의 기존 실행 기록)
- actions_for(event_id) -> list[dict]          (이 사건의 실행 기록)
- allowed_action(asset_id, event_type, action_id) -> dict | None   (그래프: 적용 SOP 가 허용한 조치와 값 범위)
- insert_action_log(event_id, approval_id, action_id, value, idem_key, status, detail) -> (row, created)
"""
from __future__ import annotations

EXECUTABLE_STATUSES = {"PENDING_APPROVAL"}
MAX_ACTION_ATTEMPTS = 1  # hydops.config.Thresholds.max_action_attempts


class PolicyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def execute_sim_action(repo, sim, event_id: str, approval_id: str | None, action_id: str, value: float, attempt: int = 1, **llm_claims) -> dict:
    """승인 ID 로 실제 승인 기록을 조회해 검사한 뒤 시뮬레이터에 명령한다.

    llm_claims(예: approved=True)는 기록만 하고 판단에 쓰지 않는다.
    """
    ev = repo.get_event(event_id)
    idem_key = f"{event_id}:{action_id}:{attempt}"

    existing = repo.find_action_log(idem_key)
    if existing:  # 재시작·중복 요청: 이미 실행한 조치를 반복하지 않는다
        return {"ok": existing["command_status"] == "SUCCEEDED", "duplicate": True, "action_log": existing}

    def reject(code, msg):
        raise PolicyError(code, msg)

    if ev is None:
        reject("EVENT_NOT_FOUND", event_id)
    if ev["status"] not in EXECUTABLE_STATUSES:
        reject("EVENT_NOT_EXECUTABLE", f"status={ev['status']}")

    # 승인은 승인 테이블의 기록만 인정한다. LLM 이 approved=true 라고 말해도 승인이 아니다.
    apr = repo.get_approval(approval_id) if approval_id else None
    if apr is None:
        reject("APPROVAL_NOT_FOUND", f"approval_id={approval_id} (claims={llm_claims})")
    if apr["event_id"] != event_id:
        reject("APPROVAL_EVENT_MISMATCH", f"{apr['event_id']} != {event_id}")
    if apr["decision"] != "APPROVED":
        reject("APPROVAL_REJECTED", apr["decision"])
    if apr["action_id"] != action_id:
        reject("ACTION_MISMATCH", f"approved {apr['action_id']} != {action_id}")

    # 요청값은 사람이 승인한 값과 같아야 한다
    if apr["approved_value"] is None or abs(apr["approved_value"] - value) > 1e-9:
        reject("VALUE_MISMATCH", f"approved {apr['approved_value']} != requested {value}")

    act = repo.allowed_action(ev["asset_id"], ev["event_type"], action_id)
    if act is None:
        reject("ACTION_NOT_ALLOWED", action_id)
    # 승인된 값이라도 SOP 허용 범위의 하한·상한을 모두 지켜야 한다
    if act.get("min_value") is not None and not (act["min_value"] <= value <= act["max_value"]):
        reject("VALUE_OUT_OF_RANGE", f"{value} not in [{act['min_value']}, {act['max_value']}]")

    prior = [a for a in repo.actions_for(event_id) if a["command_status"] == "SUCCEEDED"]
    if len(prior) >= MAX_ACTION_ATTEMPTS:
        reject("REPEAT_SUPPRESSED", f"{len(prior)} prior executions")

    commands = {"REDUCE_LOAD": sim.apply_load, "FAN_BOOST": sim.apply_fan_boost}
    result = commands[action_id](value) if action_id in commands else {"ok": False, "error": f"unsupported action {action_id}"}
    status = "SUCCEEDED" if result.get("ok") else "FAILED"
    row, created = repo.insert_action_log(event_id, approval_id, action_id, value, idem_key, status, {**result, "llm_claims_ignored": llm_claims or None})
    return {"ok": status == "SUCCEEDED", "duplicate": not created, "action_log": row}
