"""B7 · 도구를 사용하는 운영 에이전트.

- llm 모드: LangChain create_agent + 할당 Skill 프롬프트 + 구조화 결과
- offline 모드: 같은 Skill 순서를 코드로 따르는 결정적 에이전트 (API 장애·테스트 대비)
어느 모드든 마지막에 '근거 검증'을 코드로 한다: 인용이 실제 검색 결과에 없으면 HOLD.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from hydops.b3_tsdb import store
from hydops.b7_agent import tools as T
from hydops.b7_agent.skill_loader import build_system_prompt
from hydops.config import SETTINGS, TH

ASSIGNED_SKILLS = ["hydraulic-cooling-response"]


class Proposal(BaseModel):
    decision: Literal["PROPOSE", "HOLD", "SENSOR_CHECK", "ESCALATE"]
    action_id: str | None = Field(default=None, description="REDUCE_LOAD / SENSOR_CHECK / ESCALATE 등")
    value: float | None = None
    citations: list[T.Citation] = Field(default_factory=list)
    rationale: str = Field(description="한국어 3문장 이내")
    checks_passed: bool = False


def _event_prompt(ev: dict) -> str:
    return (
        f"사건 {ev['event_id']} 을 처리하라.\n"
        f"- asset_id: {ev['asset_id']}\n- event_type: {ev['event_type']}\n"
        f"- 탐지 구간: {ev['window_start']} ~ {ev['window_end']}\n- 탐지 규칙: {ev['rule_version']}\n"
        f"- 탐지 근거 요약: {json.dumps(ev['evidence'], ensure_ascii=False)}\n"
        "Skill 의 판단 순서대로 도구를 호출하고 결과 형식으로 답하라."
    )


def run_llm_agent(ev: dict, trace: list) -> Proposal:
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model=SETTINGS.llm_model, temperature=0)
    agent = create_agent(
        model=model,
        tools=T.build_tools(event_until=ev["window_end"], run_id=ev["run_id"], trace=trace),
        system_prompt=build_system_prompt(ASSIGNED_SKILLS),
        response_format=Proposal,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": _event_prompt(ev)}]})
    return result["structured_response"]


def run_offline_agent(ev: dict, trace: list) -> Proposal:
    """Skill 순서를 코드로 따른다: 센서 품질 → 설비 → SOP 검색 → 제안 검사."""
    tl = {t.name: t for t in T.build_tools(event_until=ev["window_end"], run_id=ev["run_id"], trace=trace)}
    a, et = ev["asset_id"], ev["event_type"]
    win = json.loads(tl["get_recent_window"].invoke({"asset_id": a, "seconds": 60}))
    ts = win["sensors"].get("TS1", {})
    if et == "SENSOR_FAULT" or ts.get("sensor_state") == "SENSOR_FAULT":
        sop = json.loads(tl["search_sop"].invoke({"asset_id": a, "event_type": "SENSOR_FAULT"}))
        cits = [{"doc_id": h["doc_id"], "version": h["version"], "section": h["section"]} for h in sop["hits"][:2]]
        if not cits:
            return Proposal(decision="HOLD", rationale="센서 오류 SOP 근거가 없어 보류한다.")
        return Proposal(decision="SENSOR_CHECK", action_id="SENSOR_CHECK", citations=cits, rationale="온도 센서 품질 불량으로 설비 조치를 보류하고 센서 점검을 제안한다.", checks_passed=True)
    ctx = json.loads(tl["get_asset_context"].invoke({"asset_id": a}))
    sop = json.loads(tl["search_sop"].invoke({"asset_id": a, "event_type": et}))
    equipment = [x for x in ctx.get("allowed_actions", []) if x.get("requires_approval") and x.get("default_value") is not None]
    if not sop["hits"] or not equipment:
        return Proposal(decision="HOLD", rationale="이 설비에 적용되는 냉각 이상 SOP 근거나 허용 조치가 없어 보류한다.")
    act = equipment[0]
    cits = [{"doc_id": h["doc_id"], "version": h["version"], "section": h["section"]} for h in sop["hits"][:3]]
    chk = json.loads(tl["propose_action"].invoke({"event_id": ev["event_id"], "action_id": act["action_id"], "value": act["default_value"], "citations": cits}))
    if not chk["ok"]:
        failed = [c["check"] for c in chk["checks"] if not c["ok"]]
        return Proposal(decision="ESCALATE" if "not_already_executed" in failed else "HOLD", action_id=act["action_id"], value=act["default_value"], citations=cits, rationale=f"허용 범위 검사 실패: {failed}")
    return Proposal(decision="PROPOSE", action_id=act["action_id"], value=act["default_value"], citations=cits, rationale=f"유효 온도가 {TH.alarm_temp_c}°C 초과로 {TH.alarm_sustain_s}초 이상 지속되었다. 적용 SOP 가 {act['name']}을(를) 허용한다.", checks_passed=True)


def verify_citations(p: Proposal, trace: list) -> tuple[Proposal, list[str]]:
    """근거 검증: 인용은 이번 실행의 search_sop 결과에 실제로 나온 절이어야 한다."""
    retrieved = {
        (h["doc_id"], int(h["version"]), str(h["section"]))
        for t in trace
        if t["tool"] == "search_sop"
        for h in t["result"]["hits"]
    }
    problems = [f"{c.doc_id}@v{c.version}#{c.section}" for c in p.citations if (c.doc_id, int(c.version), str(c.section)) not in retrieved]
    if p.decision in ("PROPOSE", "SENSOR_CHECK") and (problems or not p.citations):
        return Proposal(decision="HOLD", action_id=p.action_id, value=p.value, citations=[], rationale=f"근거 검증 실패로 보류: 검색되지 않은 인용 {problems or '없음'}"), problems
    return p, problems


def propose_for_event(event_id: str, mode: str | None = None) -> dict:
    ev = store.get_event(event_id)
    mode = mode or SETTINGS.agent_mode
    trace: list = []
    raw = run_llm_agent(ev, trace) if mode == "llm" else run_offline_agent(ev, trace)
    final, problems = verify_citations(raw, trace)
    return {
        "event_id": event_id,
        "mode": mode,
        "model": SETTINGS.llm_model if mode == "llm" else "offline-skill-runner",
        "proposal": final.model_dump(),
        "raw_proposal": raw.model_dump(),
        "citation_problems": problems,
        "tool_trace": [{"tool": t["tool"], "args": t["args"], "result_summary": _summarize(t)} for t in trace],
    }


def _summarize(t: dict):
    r = t["result"]
    if t["tool"] == "search_sop":
        return [f"{h['doc_id']} v{h['version']} §{h['section']} {h['heading']}" for h in r["hits"]]
    if t["tool"] == "get_recent_window":
        ts = r["sensors"].get("TS1", {})
        return {k: ts.get(k) for k in ("valid_mean", "valid_max", "longest_valid_above_alarm_s", "sensor_state")} | {"valid_ratio": ts.get("quality", {}).get("valid_ratio")}
    if t["tool"] == "get_asset_context":
        return {"sops": [f"{s['doc_id']} v{s['version']}" for s in r.get("applicable_sops", [])], "allowed": [a["action_id"] for a in r.get("allowed_actions", [])]}
    if t["tool"] == "propose_action":
        return {"ok": r.get("ok"), "failed": [c["check"] for c in r.get("checks", []) if not c["ok"]]}
    return r
