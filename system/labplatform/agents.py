"""Agents (교육용) — Skill 등록·할당, MCP 도구 서버 등록, 업무 에이전트 실행, Watch Agent.

실제 플랫폼 대응: Process GPT 업무 에이전트(할당 Skill 의 SKILL.md 로드 + MCP 도구), Ontologic Watch Agent(SQL→조건→업무 시작).
원칙: 플랫폼 개발 지원용 Skill 과 업무 에이전트가 실행 시 읽는 Skill 은 별개다. 수업에서는 짧은 SKILL.md 만 할당한다.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from typing import Literal

import yaml
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from labplatform import db, fabric

router = APIRouter(prefix="/agents", tags=["Agents"])
MAX_SKILL_CHARS = 6000


# ---- Skill ------------------------------------------------------------------------
def _parse_skill(content: str) -> dict:
    meta, body = {}, content
    if content.startswith("---"):
        _, fm, body = content.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    if not meta.get("name") or not meta.get("description"):
        raise HTTPException(422, "SKILL.md frontmatter 에 name, description 이 필요하다")
    return {"meta": meta, "body": body.strip()}


@router.post("/skills")
def register_skill(body: dict = Body(...)):
    content = body["files"]["SKILL.md"]
    parsed = _parse_skill(content)
    name = parsed["meta"]["name"]
    sk = {"name": name, "description": parsed["meta"]["description"], "version": parsed["meta"].get("version"), "files": body["files"], "chars": len(parsed["body"]), "registered_at": db.now()}
    db.put("skill", name, sk)
    db.log("agents", name, "skill registered", {"chars": sk["chars"]})
    return {k: v for k, v in sk.items() if k != "files"}


@router.get("/skills")
def list_skills():
    return [{k: v for k, v in s.items() if k != "files"} for s in db.list_("skill")]


@router.get("/skills/{name}/files/{fname}")
def skill_file(name: str, fname: str):
    sk = db.get("skill", name)
    if not sk or fname not in sk["files"]:
        raise HTTPException(404, "not found")
    return {"content": sk["files"][fname]}


# ---- MCP 서버 ---------------------------------------------------------------------
@router.post("/mcp-servers")
def register_mcp(body: dict = Body(...)):
    if body.get("type", "http") != "http" or "command" in body:
        raise HTTPException(400, "이 교육용 런타임은 streamable HTTP(type=http, url) 만 받는다 — 명령 기반 설정과 HTTP 주소를 혼용하지 않는다")
    srv = {"name": body["name"], "type": "http", "url": body["url"], "registered_at": db.now()}
    db.put("mcp_server", srv["name"], srv)
    return srv


@router.get("/mcp-servers")
def list_mcp():
    return db.list_("mcp_server")


def _client(names: list[str]):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    cfg = {}
    for n in names:
        s = db.get("mcp_server", n)
        if not s:
            raise HTTPException(404, f"mcp server {n} not registered")
        cfg[n] = {"transport": "streamable_http", "url": s["url"]}
    return MultiServerMCPClient(cfg)


def _content_to_obj(content):
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return content


@router.get("/mcp-servers/{name}/tools")
def mcp_tools(name: str):
    tools = asyncio.run(_client([name]).get_tools())
    return [{"name": t.name, "description": t.description, "args": t.args} for t in tools]


async def call_tool_async(server: str, tool: str, args: dict):
    tools = {t.name: t for t in await _client([server]).get_tools()}
    if tool not in tools:
        raise HTTPException(404, f"tool {tool} not on {server}")
    res = await tools[tool].ainvoke(args)
    return _content_to_obj(res)


@router.post("/mcp-servers/{name}/call")
def mcp_call(name: str, body: dict = Body(...)):
    return {"tool": body["tool"], "args": body.get("args", {}), "result": asyncio.run(call_tool_async(name, body["tool"], body.get("args", {})))}


# ---- 업무 에이전트 -------------------------------------------------------------------
class Citation(BaseModel):
    doc_id: str
    version: int
    section: str


class Proposal(BaseModel):
    decision: Literal["PROPOSE", "HOLD", "SENSOR_CHECK", "ESCALATE"]
    action_id: str | None = None
    value: float | None = None
    citations: list[Citation] = Field(default_factory=list)
    rationale: str = Field(description="한국어 3문장 이내")
    checks_passed: bool = False


@router.post("")
def upsert_agent(body: dict = Body(...)):
    for s in body.get("skills", []):
        if not db.get("skill", s):
            raise HTTPException(404, f"skill {s} not registered")
    ag = {"agent_id": body["agent_id"], "name": body.get("name", body["agent_id"]), "role": body.get("role", ""), "model": body.get("model", os.environ.get("HYDOPS_LLM_MODEL", "gpt-4.1-mini")), "skills": body.get("skills", []), "mcp_servers": body.get("mcp_servers", []), "allowed_tools": body.get("allowed_tools", []), "updated_at": db.now()}
    db.put("agent", ag["agent_id"], ag)
    return ag


@router.get("")
def list_agents():
    return db.list_("agent")


def system_prompt(agent: dict) -> str:
    parts = [f"너는 '{agent['name']}' 업무 에이전트다. {agent.get('role', '')}", "도구 결과와 SOP 검색 결과만 근거로 삼는다. 승인·실행 권한은 없다.", "", "[할당된 스킬 가이드]"]
    for s in agent["skills"]:
        sk = db.get("skill", s)
        body = _parse_skill(sk["files"]["SKILL.md"])["body"][:MAX_SKILL_CHARS]
        parts.append(f"### {s}\n{body}")
    return "\n".join(parts)


async def run_agent_async(agent_id: str, instruction: str) -> dict:
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_openai import ChatOpenAI

    ag = db.get("agent", agent_id)
    if not ag:
        raise HTTPException(404, f"agent {agent_id} not found")
    tools = await _client(ag["mcp_servers"]).get_tools()
    if ag["allowed_tools"]:
        tools = [t for t in tools if t.name in ag["allowed_tools"]]
    t0 = time.time()
    agent = create_agent(model=ChatOpenAI(model=ag["model"], temperature=0), tools=tools, system_prompt=system_prompt(ag), response_format=Proposal)
    out = await agent.ainvoke({"messages": [{"role": "user", "content": instruction}]})
    calls, trace = {}, []
    for m in out["messages"]:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                calls[tc["id"]] = tc
        elif isinstance(m, ToolMessage) and m.tool_call_id in calls:
            tc = calls[m.tool_call_id]
            trace.append({"tool": tc["name"], "args": tc["args"], "result": _content_to_obj(m.content)})
    sp = out.get("structured_response")
    return {
        "agent_id": agent_id,
        "model": ag["model"],
        "skills": ag["skills"],
        "tools_bound": [t.name for t in tools],
        "elapsed_s": round(time.time() - t0, 1),
        "proposal": sp.model_dump() if sp else None,
        "tool_trace_full": trace,
        "tool_trace": [{"tool": t["tool"], "args": t["args"], "result_summary": _summary(t)} for t in trace],
    }


def _summary(t: dict):
    r = t["result"]
    if not isinstance(r, dict):
        return str(r)[:200]
    if t["tool"] == "search_sop":
        return [f"{h['doc_id']} v{h['version']} §{h['section']} {h['heading']}" for h in r.get("hits", [])]
    if t["tool"] == "propose_action":
        return {"ok": r.get("ok"), "failed": [c["check"] for c in r.get("checks", []) if not c["ok"]]}
    if t["tool"] == "get_recent_window":
        ts = r.get("sensors", {}).get("TS1", {})
        return {"sensor_state": ts.get("sensor_state"), "longest_valid_above_alarm_s": ts.get("longest_valid_above_alarm_s"), "valid_max": ts.get("valid_max")}
    if t["tool"] == "get_asset_context":
        return {"sops": [f"{s['doc_id']} v{s['version']}" for s in r.get("applicable_sops", [])], "allowed": [a["action_id"] for a in r.get("allowed_actions", [])]}
    return {k: r[k] for k in list(r)[:4]}


@router.post("/{agent_id}/run")
def run_agent(agent_id: str, body: dict = Body(...)):
    return asyncio.run(run_agent_async(agent_id, body["instruction"]))


# ---- Watch Agent -------------------------------------------------------------------
@router.post("/watch")
def upsert_watch(body: dict = Body(...)):
    w = {"watch_id": body["watch_id"], "description": body.get("description", ""), "datasource": body["datasource"], "sql": body["sql"], "condition": body.get("condition", "rows > 0"), "process_def_id": body["process_def_id"], "param_map": body["param_map"], "interval_s": int(body.get("interval_s", 5)), "enabled": bool(body.get("enabled", False)), "updated_at": db.now()}
    db.put("watch", w["watch_id"], w)
    return w


@router.get("/watch")
def list_watch():
    return db.list_("watch")


def _condition(expr: str, rows: list[dict]) -> bool:
    m = re.fullmatch(r"\s*rows\s*(>=|>|==)\s*(\d+)\s*", expr)
    if not m:
        raise HTTPException(400, "condition 은 'rows > N' 형식만 지원한다")
    n = len(rows)
    return {"<": n < int(m[2]), ">": n > int(m[2]), ">=": n >= int(m[2]), "==": n == int(m[2])}[m[1]]


def watch_tick(watch_id: str) -> dict:
    """SQL → 조건 → 업무 시작. 미처리 사건 한 건만 읽는다 (다중 행 일괄 처리는 하지 않는다)."""
    from labplatform import process

    w = db.get("watch", watch_id)
    rows = fabric.query(w["datasource"], w["sql"], limit=1)
    fired = _condition(w["condition"], rows)
    result = {"watch_id": watch_id, "rows": len(rows), "condition": w["condition"], "fired": fired, "started": None}
    if fired:
        row = rows[0]
        values = {k: (row.get(v[6:-1]) if isinstance(v, str) and v.startswith("${row.") else v) for k, v in w["param_map"].items()}
        values["source"] = f"watch:{watch_id}"
        result["started"] = process.start_instance(w["process_def_id"], values)
    db.log("watch", watch_id, "tick", {k: v for k, v in result.items() if k != "started"} | {"instance": (result["started"] or {}).get("instance_id")})
    return result


@router.post("/watch/{watch_id}/tick")
def tick(watch_id: str):
    return watch_tick(watch_id)


class WatchScheduler(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__(name="watch-scheduler")
        self.last: dict[str, float] = {}

    def run(self):
        while True:
            for w in db.list_("watch"):
                if w["enabled"] and time.time() - self.last.get(w["watch_id"], 0) >= w["interval_s"]:
                    self.last[w["watch_id"]] = time.time()
                    try:
                        watch_tick(w["watch_id"])
                    except Exception as e:  # noqa: BLE001
                        db.log("watch", w["watch_id"], "error", {"error": repr(e)})
            time.sleep(1)
