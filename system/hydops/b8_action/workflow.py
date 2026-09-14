"""B8 · 승인·조치·재측정 오케스트레이션 (LangGraph, 로컬 실습용).

감지 → 근거 확인 → 승인 대기 → 실행 → 재측정 → 종결
  근거 없음 → 보류(HOLD_NO_EVIDENCE)      센서 오류 → 센서 점검(SENSOR_CHECK)
  승인 거부 → 미실행 종료(REJECTED)       도구 실패·정책 위반·미개선 → 이관(ESCALATED)
  데이터 부족 → 재측정 보류(VERIFY_HOLD) 후 다음 창에서 한 번 더 재측정

체크포인트는 PostgreSQL 에 저장된다(thread_id = event_id). 재시작 후 같은 사건을 다시 읽어도
이미 승인·실행한 조치를 반복하지 않는다 (체크포인트 + action_log 중복 키 두 겹).
플랫폼 실습(후반부)에서는 같은 service 함수를 교육용 플랫폼의 프로세스가 호출한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from hydops.b3_tsdb import store
from hydops.b8_action import service
from hydops.config import SETTINGS


class CaseState(TypedDict, total=False):
    event_id: str
    decision: str
    approval_id: str | None
    action_log_id: str | None
    wait_until: str | None
    verify_index: int
    outcome: str | None
    reverify: bool


def build_graph(runtime, agent_mode: str | None = None):
    def evidence(state: CaseState):
        result = service.gather_evidence(state["event_id"], agent_mode)
        return {"decision": result["proposal"]["decision"]}

    def approval(state: CaseState):
        ev = store.get_event(state["event_id"])
        p = ev["proposal"]["proposal"]
        # 사람 승인 태스크: 여기서 멈추고 승인 API 가 approval_id 로 재개한다
        answer = interrupt({"type": "approval", "event_id": ev["event_id"], "asset_id": ev["asset_id"], "run_id": ev["run_id"], "action_id": p["action_id"], "proposed_value": p["value"], "citations": p["citations"]})
        return {"approval_id": answer["approval_id"]}

    def execute(state: CaseState):
        apr = store.get_approval(state["approval_id"])
        if apr["decision"] != "APPROVED":
            return {"outcome": "REJECTED"}
        ev = store.get_event(state["event_id"])
        res = service.execute(runtime.sims[ev["asset_id"]], ev["event_id"], apr["approval_id"], apr["action_id"], apr["approved_value"])
        if not res["ok"]:
            return {"outcome": res.get("refused") or "COMMAND_FAILED"}
        return {"action_log_id": res["action_log"]["action_log_id"], "wait_until": res["wait_until"].isoformat(), "verify_index": 0}

    def wait_remeasure(state: CaseState):
        interrupt({"type": "wait_until", "event_id": state["event_id"], "until": state["wait_until"]})
        return {}

    def verify(state: CaseState):
        idx = state.get("verify_index", 0)
        res = service.verify(state["event_id"], state["action_log_id"], idx)
        if res.get("next_window_index") is not None:
            return {"outcome": res["outcome"], "verify_index": res["next_window_index"], "wait_until": res["wait_until"].isoformat(), "reverify": True}
        return {"outcome": res["outcome"], "reverify": False}

    g = StateGraph(CaseState)
    for name, fn in [("evidence", evidence), ("approval", approval), ("execute", execute), ("wait_remeasure", wait_remeasure), ("verify", verify)]:
        g.add_node(name, fn)
    g.add_edge(START, "evidence")
    g.add_conditional_edges("evidence", lambda s: "approval" if s["decision"] == "PROPOSE" else END, ["approval", END])
    g.add_edge("approval", "execute")
    g.add_conditional_edges("execute", lambda s: "wait_remeasure" if s.get("wait_until") else END, ["wait_remeasure", END])
    g.add_edge("wait_remeasure", "verify")
    g.add_conditional_edges("verify", lambda s: "wait_remeasure" if s.get("reverify") else END, ["wait_remeasure", END])
    return g


class Orchestrator:
    """사건별 워크플로 인스턴스를 시작·승인·재개한다."""

    def __init__(self, runtime, agent_mode: str | None = None):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        self.runtime = runtime
        self.pool = ConnectionPool(SETTINGS.pg_dsn, kwargs={"autocommit": True, "prepare_threshold": 0}, min_size=1, max_size=4, open=True)
        self.saver = PostgresSaver(self.pool)
        self.saver.setup()
        self.app = build_graph(runtime, agent_mode).compile(checkpointer=self.saver)

    @staticmethod
    def cfg(event_id: str) -> dict:
        return {"configurable": {"thread_id": event_id}}

    def snapshot(self, event_id: str) -> dict:
        st = self.app.get_state(self.cfg(event_id))
        pending = [i.value for t in st.tasks for i in (t.interrupts or [])]
        return {"values": st.values, "next": list(st.next), "interrupts": pending}

    def start(self, event_id: str) -> dict:
        snap = self.snapshot(event_id)
        if snap["values"]:  # 이미 시작된 사건: 다시 실행하지 않는다 (재시작 안전)
            return {"started": False, **snap}
        self.app.invoke({"event_id": event_id, "verify_index": 0}, self.cfg(event_id))
        return {"started": True, **self.snapshot(event_id)}

    def decide(self, event_id: str, approver: str, decision: str, value: float | None, comment: str | None = None) -> dict:
        snap = self.snapshot(event_id)
        if not any(i.get("type") == "approval" for i in snap["interrupts"]):
            ev = store.get_event(event_id)
            return {"ok": False, "error": "NOT_WAITING_FOR_APPROVAL", "status": ev["status"] if ev else None}
        rec = service.record_decision(event_id, approver, decision, value, comment)
        if not rec["ok"]:
            return rec
        self.app.invoke(Command(resume={"approval_id": rec["approval"]["approval_id"]}), self.cfg(event_id))
        return {"ok": True, "approval": rec["approval"], **self.snapshot(event_id)}

    def poll(self, now: datetime | None = None) -> list[str]:
        """재측정 대기 중인 사건 중 시각이 된 것을 재개한다."""
        resumed = []
        with store.connect() as c:
            rows = c.execute("SELECT event_id, asset_id FROM event WHERE status IN ('VERIFYING','VERIFY_HOLD') AND process_ref IS NULL").fetchall()
        for r in rows:
            waits = [i for i in self.snapshot(r["event_id"])["interrupts"] if i.get("type") == "wait_until"]
            if not waits:
                continue
            t = now or self.runtime.now(r["asset_id"])
            if t >= datetime.fromisoformat(waits[0]["until"]):
                self.app.invoke(Command(resume={"at": t.isoformat()}), self.cfg(r["event_id"]))
                resumed.append(r["event_id"])
        return resumed

    def close(self):
        self.pool.close()
