"""Process (교육용) — 업무 프로세스 정의·인스턴스·사람 태스크(워크리스트)·실행 엔진.

실제 플랫폼 대응: Process GPT 프로세스 정의(활동·폼·게이트웨이)와 업무 인스턴스.
원칙 (실라버스 'Skill과 조치 프로세스 계약'):
- 접수 폼과 조치 승인 태스크를 분리한다. event_id·asset_id·run_id·제안값·근거 참조를 실제 입력 폼에 매핑한다.
- 시작 API 재호출만으로 중복이 방지된다고 가정하지 않는다 → 인스턴스 키(def:event_id:회차)를 명시적으로 등록한다.
- 프로세스의 완료 상태는 업무 진행을 나타내며 설비 회복을 대체하지 않는다 (equipment_outcome 을 따로 둔다).
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import httpx
from fastapi import APIRouter, Body, HTTPException

from labplatform import agents, db

router = APIRouter(prefix="/process", tags=["Process"])
HYDOPS_API = os.environ.get("HYDOPS_API", "http://localhost:8800")
SYSTEM_TOKEN = os.environ.get("HYDOPS_SYSTEM_TOKEN", "lab-system-token")
_VAR = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")


# ---- 변수 치환·조건 -------------------------------------------------------------------
def _lookup(vars_: dict, path: str):
    cur = vars_
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def render(tpl, vars_: dict):
    if isinstance(tpl, str):
        m = _VAR.fullmatch(tpl)
        if m:
            return _lookup(vars_, m[1])
        return _VAR.sub(lambda x: str(_lookup(vars_, x[1]) if x[1] != "HYDOPS_API" else HYDOPS_API), tpl)
    if isinstance(tpl, dict):
        return {k: render(v, vars_) for k, v in tpl.items()}
    if isinstance(tpl, list):
        return [render(v, vars_) for v in tpl]
    return tpl


def cond_ok(c: dict | None, vars_: dict) -> bool:
    if not c:
        return True
    if "all" in c:
        return all(cond_ok(x, vars_) for x in c["all"])
    v = _lookup(vars_, c["var"])
    return {"==": v == c.get("value"), "!=": v != c.get("value"), "in": v in (c.get("value") or []), "truthy": bool(v)}[c["op"]]


# ---- 정의 ---------------------------------------------------------------------------
@router.post("/definitions")
def upsert_definition(body: dict = Body(...)):
    ids = {a["id"] for a in body["activities"]}
    for t in body["transitions"]:
        if t["from"] not in ids or t["to"] not in ids:
            raise HTTPException(422, f"transition {t} 의 활동이 정의에 없다")
    body = {**body, "updated_at": db.now()}
    db.put("process_def", body["def_id"], body)
    return {"def_id": body["def_id"], "activities": len(body["activities"])}


@router.get("/definitions")
def list_definitions():
    return [{"def_id": d["def_id"], "name": d["name"], "version": d.get("version"), "description": d.get("description"), "activities": [{"id": a["id"], "name": a["name"], "type": a["type"]} for a in d["activities"]]} for d in db.list_("process_def")]


@router.get("/definitions/{def_id}")
def get_definition(def_id: str):
    d = db.get("process_def", def_id)
    if not d:
        raise HTTPException(404, "not found")
    return d


# ---- 인스턴스 ------------------------------------------------------------------------
def _activity(defn: dict, aid: str) -> dict:
    return next(a for a in defn["activities"] if a["id"] == aid)


def start_instance(def_id: str, values: dict, attempt: int = 1) -> dict:
    defn = db.get("process_def", def_id)
    if not defn:
        raise HTTPException(404, f"process {def_id} not found")
    first = defn["activities"][0]
    missing = [f["name"] for f in first.get("fields", []) if f.get("required") and values.get(f["name"]) in (None, "")]
    if missing:
        raise HTTPException(422, {"error": "접수 폼 필수 입력 누락", "missing": missing})
    key_field = defn.get("instance_key", "event_id")
    key = f"{def_id}:{values[key_field]}:{attempt}"
    instance_id = f"PI-{uuid.uuid4().hex[:8]}"
    if not db.insert_new("instance_key", key, {"key": key, "instance_id": instance_id}):
        existing = db.get("instance_key", key)
        db.log("process", existing["instance_id"], "duplicate start refused", {"key": key})
        return {"duplicate": True, "instance_id": existing["instance_id"], "key": key}
    inst = {
        "instance_id": instance_id,
        "def_id": def_id,
        "def_name": defn["name"],
        "key": key,
        "status": "RUNNING",
        "equipment_outcome": None,
        "vars": {**defn.get("defaults", {}), **values, "instance_id": instance_id, "def_id": def_id, "instance_key": key},
        "steps": [{"activity_id": first["id"], "name": first["name"], "type": first["type"], "status": "DONE", "started_at": db.now(), "ended_at": db.now(), "input": values, "output": {}}],
        "created_at": db.now(),
    }
    _advance(inst, defn, first["id"])
    db.put("instance", instance_id, inst)
    db.log("process", instance_id, "started", {"key": key, "values": values})
    return {"duplicate": False, "instance_id": instance_id, "key": key}


def _advance(inst: dict, defn: dict, from_id: str) -> None:
    nxt = next((t["to"] for t in defn["transitions"] if t["from"] == from_id and cond_ok(t.get("when"), inst["vars"])), None)
    if nxt is None:
        inst["status"] = "COMPLETED"
        return
    a = _activity(defn, nxt)
    step = {"activity_id": a["id"], "name": a["name"], "type": a["type"], "status": "WAITING_HUMAN" if a["type"] == "human" else "READY", "started_at": db.now(), "input": None, "output": None, "attempts": 0}
    if a["type"] == "human":
        step["form"] = [{**f, "value": render(f.get("default"), inst["vars"])} for f in a["fields"]]
        step["role"] = a.get("role")
    inst["steps"].append(step)
    if a["type"] == "end":
        step.update(status="DONE", ended_at=db.now(), output={"result": render(a.get("result"), inst["vars"])})
        inst["status"] = "COMPLETED"
        inst["business_result"] = a.get("label", a["name"])
        inst["equipment_outcome"] = inst["vars"].get("outcome")


def _run_step(inst: dict, defn: dict, step: dict) -> None:
    a = _activity(defn, step["activity_id"])
    v = inst["vars"]
    step["status"] = "IN_PROGRESS"
    step["attempts"] = step.get("attempts", 0) + 1
    if a["type"] == "http":
        url = render(a["url"], v)
        body = render(a.get("body", {}), v)
        step["input"] = {"method": a.get("method", "POST"), "url": url, "body": body}
        r = httpx.request(a.get("method", "POST"), url, json=body, headers={"X-Lab-System-Token": SYSTEM_TOKEN}, timeout=60)
        res = r.json()
        step["output"] = {"http_status": r.status_code, "response": res}
        if r.status_code >= 400:
            raise RuntimeError(f"{url} → {r.status_code} {res}")
        v.update({k: _lookup({"response": res}, p) for k, p in a.get("outputs", {}).items()})
    elif a["type"] == "agent":
        instruction = render(a["instruction"], v)
        step["input"] = {"agent_id": a["agent_id"], "instruction": instruction}
        res = asyncio.run(agents.run_agent_async(a["agent_id"], instruction))
        step["output"] = {k: res[k] for k in ("agent_id", "model", "skills", "tools_bound", "elapsed_s", "proposal", "tool_trace")}
        v["agent_result"] = res
        v.update({k: _lookup({"result": res}, p) for k, p in a.get("outputs", {}).items()})
    elif a["type"] == "tool":
        args = render(a["args"], v)
        step["input"] = {"server": a["server"], "tool": a["tool"], "args": args}
        res = asyncio.run(agents.call_tool_async(a["server"], a["tool"], args))
        step["output"] = res
        ru = a.get("retry_until")
        if ru and _lookup({"result": res}, ru["path"]) != ru["equals"]:
            for k, p in ru.get("update_vars", {}).items():
                val = _lookup({"result": res}, p)
                if val is not None:
                    v[k] = val
            step["status"] = "RETRY"
            step["next_try_at"] = time.time() + ru.get("interval_s", 3)
            step["note"] = f"대기 중: {res.get('wait_until') if isinstance(res, dict) else ''}"
            return
        v.update({k: _lookup({"result": res}, p) for k, p in a.get("outputs", {}).items()})
    step["status"] = "DONE"
    step["ended_at"] = db.now()
    _advance(inst, defn, a["id"])


_locks: dict[str, threading.Lock] = {}


def process_instance(instance_id: str) -> None:
    lock = _locks.setdefault(instance_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        inst = db.get("instance", instance_id)
        defn = db.get("process_def", inst["def_id"])
        for _ in range(10):
            if inst["status"] != "RUNNING":
                break
            step = inst["steps"][-1]
            if step["status"] == "RETRY" and time.time() < step.get("next_try_at", 0):
                break
            if step["status"] not in ("READY", "RETRY"):
                break
            try:
                _run_step(inst, defn, step)
            except Exception as e:  # noqa: BLE001 — 실패 분기는 인스턴스에 기록한다
                step.update(status="ERROR", ended_at=db.now(), error=str(e)[:800])
                inst["status"] = "FAILED"
                db.log("process", instance_id, "step error", {"activity": step["activity_id"], "error": str(e)[:800]})
            db.put("instance", instance_id, inst)
    finally:
        lock.release()


class Engine(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__(name="process-engine")
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.inflight: set = set()

    def run(self):
        while True:
            for inst in db.list_("instance"):
                if inst["status"] == "RUNNING" and inst["steps"][-1]["status"] in ("READY", "RETRY") and inst["instance_id"] not in self.inflight:
                    self.inflight.add(inst["instance_id"])
                    self.pool.submit(self._work, inst["instance_id"])
            time.sleep(1)

    def _work(self, iid):
        try:
            process_instance(iid)
        finally:
            self.inflight.discard(iid)


@router.post("/definitions/{def_id}/start")
def start(def_id: str, body: dict = Body(...)):
    return start_instance(def_id, body.get("values", {}), int(body.get("attempt", 1)))


@router.get("/instances")
def list_instances():
    return [{"instance_id": i["instance_id"], "def_name": i["def_name"], "key": i["key"], "status": i["status"], "current": i["steps"][-1]["name"], "current_status": i["steps"][-1]["status"], "event_id": i["vars"].get("event_id"), "equipment_outcome": i.get("equipment_outcome"), "created_at": i["created_at"]} for i in reversed(db.list_("instance"))]


@router.get("/instances/{instance_id}")
def get_instance(instance_id: str):
    inst = db.get("instance", instance_id)
    if not inst:
        raise HTTPException(404, "not found")
    out = deepcopy(inst)
    out["vars"].pop("agent_result", None)
    out["logs"] = db.logs("process", instance_id)
    return out


@router.get("/worklist")
def worklist(role: str | None = None):
    items = []
    for i in db.list_("instance"):
        s = i["steps"][-1]
        if i["status"] == "RUNNING" and s["status"] == "WAITING_HUMAN" and (role is None or s.get("role") == role):
            items.append({"workitem_id": f"{i['instance_id']}:{s['activity_id']}", "instance_id": i["instance_id"], "activity": s["name"], "role": s.get("role"), "event_id": i["vars"].get("event_id"), "asset_id": i["vars"].get("asset_id"), "form": s["form"], "since": s["started_at"]})
    return items


@router.post("/workitems/{workitem_id}/complete")
def complete(workitem_id: str, body: dict = Body(...)):
    instance_id, activity_id = workitem_id.split(":", 1)
    inst = db.get("instance", instance_id)
    if not inst:
        raise HTTPException(404, "instance not found")
    step = inst["steps"][-1]
    if step["activity_id"] != activity_id or step["status"] != "WAITING_HUMAN":
        raise HTTPException(409, {"error": "이미 처리됐거나 대기 중인 태스크가 아니다", "status": step["status"]})
    values = body.get("values", {})
    missing = [f["name"] for f in step["form"] if f.get("required") and not f.get("readonly") and values.get(f["name"]) in (None, "")]
    if missing:
        raise HTTPException(422, {"error": "필수 입력 누락", "missing": missing})
    defn = db.get("process_def", inst["def_id"])
    editable = {f["name"] for f in step["form"] if not f.get("readonly")}
    clean = {k: v for k, v in values.items() if k in editable}
    inst["vars"].update(clean)
    step.update(status="DONE", ended_at=db.now(), output=clean, completed_by=values.get("approver", "user"))
    _advance(inst, defn, activity_id)
    db.put("instance", instance_id, inst)
    db.log("process", instance_id, f"workitem completed: {activity_id}", clean)
    return {"ok": True, "instance_id": instance_id, "next": inst["steps"][-1]["name"], "status": inst["status"]}
