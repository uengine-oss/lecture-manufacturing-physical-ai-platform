"""B8 · 사건 처리 서비스 — 로컬 LangGraph 워크플로와 교육용 플랫폼 프로세스가 같은 함수를 쓴다.

각 함수는 상태 전이와 기록을 함께 남긴다. 판단(승인·범위·중복)은 모두 executor 의 코드 검사에 있다.
"""
from __future__ import annotations

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph as kg
from hydops.b7_agent.agent import propose_for_event
from hydops.b8_action import executor
from hydops.config import TH

class EvidenceRefused(Exception):
    """감지 상태가 아닌 사건에 근거를 다시 기록하려 할 때."""

    def __init__(self, status):
        super().__init__(f"event status is {status}, expected DETECTED")
        self.status = status


TERMINAL = {"CLOSED", "ESCALATED", "REJECTED", "HOLD_NO_EVIDENCE", "SENSOR_CHECK", "RUN_ENDED"}
MAX_VERIFY_WINDOWS = 2


def to(event_id: str, status: str, actor: str, detail: dict | None = None, reason: str | None = None, **fields) -> dict:
    row = store.transition(event_id, status, actor, detail, reason, **fields)
    prop = row.get("proposal") or {}
    kg.upsert_event_ref(event_id, row["asset_id"], row["event_type"], status, (prop.get("proposal") or {}).get("citations"))
    return row


def gather_evidence(event_id: str, agent_mode: str | None = None, proposal_result: dict | None = None) -> dict:
    """근거 확인: 에이전트 제안을 받아 기록하고 다음 상태를 정한다.

    proposal_result 를 주면(플랫폼 업무 에이전트가 만든 제안) 인용 검증만 다시 하고 기록한다.
    이미 근거 확인을 지난 사건(다른 인스턴스가 처리 중이거나 끝난 사건)은 되돌리지 않는다.
    """
    ev = store.get_event(event_id)
    if ev is None or ev["status"] != "DETECTED":
        raise EvidenceRefused(ev["status"] if ev else None)
    result = proposal_result or propose_for_event(event_id, agent_mode)
    p = result["proposal"]
    to(event_id, "EVIDENCE_READY", f"agent:{result.get('model', 'platform')}", {"decision": p["decision"], "citations": p["citations"], "tool_calls": [t["tool"] for t in result.get("tool_trace", [])]}, proposal=result)
    if p["decision"] == "PROPOSE":
        to(event_id, "PENDING_APPROVAL", "orchestrator", {"action_id": p["action_id"], "value": p["value"]})
    elif p["decision"] == "SENSOR_CHECK":
        to(event_id, "SENSOR_CHECK", "orchestrator", {"note": "설비 조치 보류, 센서 점검 요청"}, reason="센서 오류")
    elif p["decision"] == "ESCALATE":
        to(event_id, "ESCALATED", "orchestrator", {"rationale": p["rationale"]}, reason="제안 검사: 반복 조치 억제")
    else:
        to(event_id, "HOLD_NO_EVIDENCE", "orchestrator", {"rationale": p["rationale"]}, reason="근거 없음")
    return result


def record_decision(event_id: str, approver: str, decision: str, value: float | None, comment: str | None = None) -> dict:
    """사람 승인 기록. 승인 대기 상태의 사건에만 한 번 받는다 (중복 요청 거부)."""
    ev = store.get_event(event_id)
    if ev is None or ev["status"] != "PENDING_APPROVAL":
        return {"ok": False, "error": "NOT_WAITING_FOR_APPROVAL", "status": ev["status"] if ev else None}
    if store.approvals_for(event_id):
        return {"ok": False, "error": "DUPLICATE_DECISION", "status": ev["status"]}
    action_id = ev["proposal"]["proposal"]["action_id"]
    apr = store.record_approval(event_id, approver, decision, action_id, value, comment)
    store.transition(event_id, "PENDING_APPROVAL", f"human:{approver}", {"approval_id": apr["approval_id"], "decision": decision, "value": value, "comment": comment})
    if decision != "APPROVED":
        to(event_id, "REJECTED", f"human:{approver}", {"approval_id": apr["approval_id"]}, reason="승인 거부 — 미실행 종료")
    return {"ok": True, "approval": apr}


def execute(sim, event_id: str, approval_id: str | None, action_id: str = "REDUCE_LOAD", value: float | None = None, **llm_claims) -> dict:
    """실행: 코드가 승인 기록을 검사한다. 정책 위반·명령 실패는 이관한다."""
    try:
        res = executor.execute_sim_action(sim, event_id, approval_id, action_id, value, **llm_claims)
    except executor.PolicyError as e:
        ev = store.get_event(event_id)
        # 승인 없는 호출(예: LLM 이 approved=true 를 주장)은 사건 상태를 바꾸지 않고 거부만 기록한다
        if e.code in ("APPROVAL_NOT_FOUND", "EVENT_NOT_EXECUTABLE", "EVENT_NOT_FOUND"):
            if ev:
                store.transition(event_id, ev["status"], "executor", {"refused": e.code, "message": str(e)})
            return {"ok": False, "refused": e.code, "message": str(e)}
        to(event_id, "ESCALATED", "executor", {"policy_error": e.code, "message": str(e)}, reason=f"조치 도구 거부: {e.code}")
        return {"ok": False, "refused": e.code, "message": str(e)}
    log = res["action_log"]
    if res["duplicate"]:
        return {"ok": res["ok"], "duplicate": True, "action_log": log}
    if not res["ok"]:
        to(event_id, "ESCALATED", "executor", {"action_log_id": log["action_log_id"], "command": log["command_detail"]}, reason="도구 실패 — 이관")
        return {"ok": False, "command_failed": True, "action_log": log}
    _, until = executor.verify_window(log, TH, 0)
    to(event_id, "EXECUTED", "executor", {"action_log_id": log["action_log_id"], "approval_id": approval_id, "value": value, "sim_ts": log["sim_ts"]})
    to(event_id, "VERIFYING", "orchestrator", {"wait_until": until})
    return {"ok": True, "action_log": log, "wait_until": until}


def verify(event_id: str, action_log_id: str, window_index: int = 0, now=None) -> dict:
    """재측정: 시각이 되지 않았으면 ready=False. 데이터 부족이면 다음 창을 알려준다."""
    act = store.get_action_log(action_log_id)
    _, end = executor.verify_window(act, TH, window_index)
    if now is not None and now < end:
        return {"ready": False, "final": False, "wait_until": end}
    res = executor.verify_recovery(action_log_id, TH, window_index=window_index)
    ver = res["verification"]
    detail = {"verification_id": ver["verification_id"], "outcome": res["outcome"], "metrics": ver["metrics"]}
    if res["outcome"] == "RECOVERED":
        to(event_id, "CLOSED", "verifier", detail, reason="재측정 회복 — 종결")
    elif res["outcome"] == "NOT_IMPROVED":
        to(event_id, "ESCALATED", "verifier", detail, reason="조치 후 미개선 — 담당자 이관")
    elif window_index + 1 < MAX_VERIFY_WINDOWS:
        _, nxt = executor.verify_window(act, TH, window_index + 1)
        to(event_id, "VERIFY_HOLD", "verifier", detail | {"next_window_until": nxt}, reason="데이터 부족 — 재측정 보류")
        return {"ready": True, "final": False, "outcome": res["outcome"], "next_window_index": window_index + 1, "wait_until": nxt, "verification": ver}
    else:
        to(event_id, "VERIFY_HOLD", "verifier", detail, reason="데이터 부족 지속 — 센서 점검 필요, 회복 판정 보류")
    return {"ready": True, "final": True, "outcome": res["outcome"], "verification": ver}
