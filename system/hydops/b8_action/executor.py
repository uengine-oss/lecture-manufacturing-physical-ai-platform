"""B8 · 조치 실행과 재측정.

조치 도구는 허용 조치 목록, 값 범위, 승인 상태, 사건 유효성, 중복 키를 '코드에서' 확인한다.
LLM 이 만든 approved=true 를 승인으로 인정하지 않는다 — 승인 테이블의 기록만 인정한다.
명령 성공(action_log.command_status)과 회복 성공(verification.outcome)은 별도 필드로 저장한다.
"""
from __future__ import annotations

from datetime import timedelta

from hydops.b2_quality.checks import OK
from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.config import TH, Thresholds

EXECUTABLE_STATUSES = {"PENDING_APPROVAL"}


class PolicyError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def allowed_action(asset_id: str, event_type: str, action_id: str) -> dict | None:
    for sop in graph.applicable_sops(asset_id, event_type):
        for a in sop["allowed_actions"]:
            if a["action_id"] == action_id:
                return a
    return None


def propose_action(event_id: str, action_id: str, value: float | None, citations: list[dict]) -> dict:
    """제안과 허용 범위 검사 결과. 실행하지 않는다."""
    ev = store.get_event(event_id)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    if not check("event_exists", ev is not None, event_id):
        return {"ok": False, "checks": checks}
    check("event_open", ev["status"] in ("DETECTED", "EVIDENCE_READY", "PENDING_APPROVAL"), ev["status"])
    act = allowed_action(ev["asset_id"], ev["event_type"], action_id)
    check("action_allowed_by_sop", act is not None, f"{action_id} for {ev['asset_id']}")
    if act and act.get("min_value") is not None:
        check("value_in_range", value is not None and act["min_value"] <= value <= act["max_value"], f"{value} in [{act['min_value']}, {act['max_value']}]")
    check("has_citation", len(citations) > 0, f"{len(citations)} citations")
    prior = [a for a in store.actions_for(event_id) if a["command_status"] == "SUCCEEDED"]
    check("not_already_executed", len(prior) < TH.max_action_attempts, f"{len(prior)} prior executions")
    return {"ok": all(c["ok"] for c in checks), "event_id": event_id, "action_id": action_id, "value": value, "checks": checks}


def execute_sim_action(sim, event_id: str, approval_id: str | None, action_id: str, value: float, attempt: int = 1, **llm_claims) -> dict:
    """승인 ID 로 실제 승인 기록을 조회해 검사한 뒤 시뮬레이터에 명령한다.

    llm_claims(예: approved=True)는 기록만 하고 판단에 쓰지 않는다.
    """
    ev = store.get_event(event_id)
    idem_key = f"{event_id}:{action_id}:{attempt}"

    existing = store.find_action_log(idem_key)
    if existing:  # 재시작·중복 요청: 이미 실행한 조치를 반복하지 않는다
        return {"ok": existing["command_status"] == "SUCCEEDED", "duplicate": True, "action_log": existing}

    def reject(code, msg):
        raise PolicyError(code, msg)

    if ev is None:
        reject("EVENT_NOT_FOUND", event_id)
    if ev["status"] not in EXECUTABLE_STATUSES:
        reject("EVENT_NOT_EXECUTABLE", f"status={ev['status']}")
    apr = store.get_approval(approval_id) if approval_id else None
    if apr is None:
        reject("APPROVAL_NOT_FOUND", f"approval_id={approval_id} (claims={llm_claims})")
    if apr["event_id"] != event_id:
        reject("APPROVAL_EVENT_MISMATCH", f"{apr['event_id']} != {event_id}")
    if apr["decision"] != "APPROVED":
        reject("APPROVAL_REJECTED", apr["decision"])
    if apr["action_id"] != action_id:
        reject("ACTION_MISMATCH", f"approved {apr['action_id']} != {action_id}")
    if apr["approved_value"] is None or abs(apr["approved_value"] - value) > 1e-9:
        reject("VALUE_MISMATCH", f"approved {apr['approved_value']} != requested {value}")
    act = allowed_action(ev["asset_id"], ev["event_type"], action_id)
    if act is None:
        reject("ACTION_NOT_ALLOWED", action_id)
    if act.get("min_value") is not None and not (act["min_value"] <= value <= act["max_value"]):
        reject("VALUE_OUT_OF_RANGE", f"{value} not in [{act['min_value']}, {act['max_value']}]")
    prior = [a for a in store.actions_for(event_id) if a["command_status"] == "SUCCEEDED"]
    if len(prior) >= TH.max_action_attempts:
        reject("REPEAT_SUPPRESSED", f"{len(prior)} prior executions")

    commands = {"REDUCE_LOAD": sim.apply_load, "FAN_BOOST": sim.apply_fan_boost}
    result = commands[action_id](value) if action_id in commands else {"ok": False, "error": f"unsupported action {action_id}"}
    status = "SUCCEEDED" if result.get("ok") else "FAILED"
    row, created = store.insert_action_log(event_id, approval_id, action_id, value, idem_key, status, {**result, "llm_claims_ignored": llm_claims or None}, sim_ts=sim.state.t)
    return {"ok": status == "SUCCEEDED", "duplicate": not created, "action_log": row}


def verify_window(act: dict, th: Thresholds = TH, window_index: int = 0):
    start = act["sim_ts"] + timedelta(seconds=th.verify_wait_s + window_index * th.verify_window_s)
    return start, start + timedelta(seconds=th.verify_window_s)


def verify_recovery(action_log_id: str, th: Thresholds = TH, now=None, window_index: int = 0) -> dict:
    """조치 이후 관측만 보고 회복·미개선·데이터 부족을 판정한다. 데이터 부족이면 다음 창(window_index+1)으로 다시 잰다."""
    act = store.get_action_log(action_log_id)
    ev = store.get_event(act["event_id"])
    start, _ = verify_window(act, th, window_index)
    end = start + timedelta(seconds=th.verify_window_s)
    if now is not None and now < end:
        return {"ready": False, "wait_until": end}
    rows = store.observations_between(ev["asset_id"], "TS1", start, end, run_id=ev["run_id"])
    valid = [r for r in rows if r["quality_flag"] == OK and r["value"] is not None]
    ratio = len(valid) / th.verify_window_s
    run = best = 0
    for r in rows:
        if r["quality_flag"] == OK and r["value"] is not None and r["value"] <= th.recovery_temp_c:
            run += 1
            best = max(best, run)
        elif r["quality_flag"] == OK:
            run = 0
    metrics = {
        "window_index": window_index,
        "window_s": th.verify_window_s,
        "valid_samples": len(valid),
        "valid_ratio": round(ratio, 3),
        "recovery_temp_c": th.recovery_temp_c,
        "longest_below_s": best,
        "required_below_s": th.recovery_sustain_s,
        "mean_c": round(sum(r["value"] for r in valid) / len(valid), 2) if valid else None,
        "last_c": round(valid[-1]["value"], 2) if valid else None,
        "command_status": act["command_status"],
    }
    if ratio < th.verify_min_valid_ratio:
        outcome = "INSUFFICIENT_DATA"
    elif best >= th.recovery_sustain_s:
        outcome = "RECOVERED"
    else:
        outcome = "NOT_IMPROVED"
    ver = store.insert_verification(action_log_id, act["event_id"], start, end, outcome, metrics)
    return {"ready": True, "outcome": outcome, "verification": ver}
