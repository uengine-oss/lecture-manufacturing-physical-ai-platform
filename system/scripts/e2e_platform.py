"""플랫폼 폐루프 통합 검증 — 수업 직전 강사 리허설 (실라버스: 한 사건의 감지·조회·승인·조치·재측정과 네 가지 실패 사례).

전제: hydops API (ORCHESTRATION=platform, :8800) 와 교육용 플랫폼(:8910)이 떠 있고 bootstrap --all 을 마쳤다.
결과: out/e2e_platform_report.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
H, P = "http://localhost:8800", "http://localhost:8910"
c = httpx.Client(timeout=120)
report: dict = {"cases": []}


def j(r):
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.url} {r.status_code} {r.text[:300]}")
    return r.json()


def wait(fn, timeout=240, every=1.0, what=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise TimeoutError(what)


def fresh(seed=42):
    j(c.post(f"{H}/api/control", json={"reset": True, "seed": seed, "scenario": "e2e-platform"}))
    time.sleep(3)


def new_event(asset, kind, etype):
    j(c.post(f"{H}/api/sim/{asset}/inject", json={"kind": kind}))
    return wait(lambda: next((e for e in j(c.get(f"{H}/api/events")) if e["asset_id"] == asset and e["event_type"] == etype), None), 120, what="event")


def start_by_watch(ev):
    tick = j(c.post(f"{P}/agents/watch/hydops-new-events/tick"))
    assert tick["fired"] and tick["started"], tick
    iid = tick["started"]["instance_id"]
    dup = j(c.post(f"{P}/process/definitions/cooling_response/start", json={"values": {"event_id": ev["event_id"], "asset_id": ev["asset_id"], "run_id": ev["run_id"], "event_type": ev["event_type"]}}))
    return iid, tick, dup


def instance(iid):
    return j(c.get(f"{P}/process/instances/{iid}"))


def workitem(iid):
    w = wait(lambda: next((w for w in j(c.get(f"{P}/process/worklist")) if w["instance_id"] == iid), None) or (instance(iid)["status"] != "RUNNING" and {"ended": True}), 180, what="workitem")
    if w.get("ended"):
        inst = instance(iid)
        raise RuntimeError(f"승인 태스크 전에 인스턴스가 끝났다: {[(s['name'], s['status'], s.get('error')) for s in inst['steps']]}")
    return w


def finish(iid):
    return wait(lambda: (lambda i: i if i["status"] != "RUNNING" else None)(instance(iid)), 300, 2, what="instance end")


def summarize(name, ev, iid, extra=None):
    inst = instance(iid)
    detail = j(c.get(f"{H}/api/events/{ev['event_id']}"))
    case = {
        "case": name,
        "event_id": ev["event_id"],
        "instance_id": iid,
        "process_status": inst["status"],
        "business_result": inst.get("business_result"),
        "equipment_outcome": inst.get("equipment_outcome"),
        "steps": [f"{s['name']}:{s['status']}" for s in inst["steps"]],
        "event_status": detail["event"]["status"],
        "event_process_ref": (detail["event"]["process_ref"] or {}).get("instance_id"),
        "actions": [a["command_status"] for a in detail["actions"]],
        "verifications": [v["outcome"] for v in detail["verifications"]],
        "approvals": [(a["approver"], a["decision"], a["approved_value"]) for a in detail["approvals"]],
        "tool_calls": [t["tool"] for t in (detail["event"].get("proposal") or {}).get("tool_trace", [])],
        **(extra or {}),
    }
    print(json.dumps(case, ensure_ascii=False))
    report["cases"].append(case)
    return case


def case_recover():
    fresh(42)
    ev = new_event("HYD-01", "cooling", "COOLING_ANOMALY")
    iid, tick, dup = start_by_watch(ev)
    w = workitem(iid)
    form = {f["name"]: f.get("value") for f in w["form"]}
    j(c.post(f"{P}/process/workitems/{w['workitem_id']}/complete", json={"values": {"decision": "APPROVED", "approved_value": form["approved_value"], "approver": "kim.operator", "comment": "SOP-LOAD-001 확인"}}))
    again = c.post(f"{P}/process/workitems/{w['workitem_id']}/complete", json={"values": {"decision": "APPROVED", "approved_value": 0.8, "approver": "kim.operator"}})
    finish(iid)
    golden = j(c.post(f"{P}/studio/schemas/HydraulicOps/golden", json={"params": {"asset_id": "HYD-01", "event_id": ev["event_id"]}}))
    report["golden"] = golden
    s = summarize("정상 회복", ev, iid, {"duplicate_start": dup, "second_completion_http": again.status_code, "form_prefilled": {k: form[k] for k in ("event_id", "asset_id", "run_id", "action_id", "proposed_value")}, "golden_answered": [g["answered"] for g in golden["results"]]})
    assert s["event_status"] == "CLOSED" and s["equipment_outcome"] == "RECOVERED" and dup["duplicate"] and again.status_code == 409
    assert s["event_process_ref"] == iid and all(s["golden_answered"])


def approve_case(name, inject, decision, value, expect_event, expect_business):
    fresh(42)
    ev = new_event("HYD-01", inject, "COOLING_ANOMALY")
    iid, _, _ = start_by_watch(ev)
    w = workitem(iid)
    j(c.post(f"{P}/process/workitems/{w['workitem_id']}/complete", json={"values": {"decision": decision, "approved_value": value, "approver": "kim.operator"}}))
    finish(iid)
    s = summarize(name, ev, iid)
    assert s["event_status"] == expect_event and s["business_result"] == expect_business, s


def case_command_fail():
    fresh(42)
    ev = new_event("HYD-01", "cooling", "COOLING_ANOMALY")
    iid, _, _ = start_by_watch(ev)
    w = workitem(iid)
    j(c.post(f"{H}/api/sim/HYD-01/inject", json={"kind": "fail_command"}))  # 다음 명령이 액추에이터 타임아웃
    j(c.post(f"{P}/process/workitems/{w['workitem_id']}/complete", json={"values": {"decision": "APPROVED", "approved_value": 0.8, "approver": "kim.operator"}}))
    finish(iid)
    s = summarize("도구(명령) 실패", ev, iid)
    assert s["event_status"] == "ESCALATED" and s["actions"] == ["FAILED"] and not s["verifications"], s


def case_second_instance_refused():
    """다른 정의로 같은 사건을 다시 처리하려 하면 근거 기록 단계에서 409 로 막힌다."""
    first = report["cases"][0]
    d = j(c.get(f"{P}/process/definitions/cooling_response"))
    d = {**d, "def_id": "cooling_response_copy", "name": "냉각 이상 대응(복제)"}
    j(c.post(f"{P}/process/definitions", json=d))
    ev = j(c.get(f"{H}/api/events/{first['event_id']}"))["event"]
    r = j(c.post(f"{P}/process/definitions/cooling_response_copy/start", json={"values": {k: ev[k] for k in ("event_id", "asset_id", "run_id", "event_type")}}))
    inst = finish(r["instance_id"])
    step = next(x for x in inst["steps"] if x["activity_id"] in ("bind", "record_evidence") and x["status"] == "ERROR") if inst["status"] == "FAILED" else None
    after = j(c.get(f"{H}/api/events/{first['event_id']}"))["event"]["status"]
    case = {"case": "이미 처리된 사건의 두 번째 인스턴스", "instance_id": r["instance_id"], "process_status": inst["status"], "failed_step": step and step["name"], "error": step and step.get("error", "")[:160], "event_status_after": after}
    print(json.dumps(case, ensure_ascii=False))
    report["cases"].append(case)
    from labplatform import db as lpdb  # 리허설용 복제 정의는 남기지 않는다 (인스턴스 기록은 증거로 둔다)
    lpdb.delete("process_def", "cooling_response_copy")
    assert inst["status"] == "FAILED" and after == "CLOSED", case


def case_sensor():
    fresh(42)
    ev = new_event("HYD-01", "dropout", "SENSOR_FAULT")
    iid, _, _ = start_by_watch(ev)
    finish(iid)
    s = summarize("센서 오류", ev, iid)
    assert s["event_status"] == "SENSOR_CHECK" and not s["actions"]


if __name__ == "__main__":
    only = sys.argv[1:] or ["recover", "reject", "not_improved", "out_of_range", "command_fail", "sensor", "second_instance"]
    t0 = time.time()
    if "recover" in only:
        case_recover()
    if "reject" in only:
        approve_case("승인 거부", "cooling", "REJECTED", None, "REJECTED", "승인 거부")
    if "not_improved" in only:
        approve_case("조치 후 미개선", "severe", "APPROVED", 0.8, "ESCALATED", "이관")
    if "out_of_range" in only:
        approve_case("허용 범위 이탈", "cooling", "APPROVED", 0.4, "ESCALATED", "이관")
    if "command_fail" in only:
        case_command_fail()
    if "sensor" in only:
        case_sensor()
    if "second_instance" in only and "recover" in only:
        case_second_instance_refused()
    report["elapsed_s"] = round(time.time() - t0, 1)
    (ROOT / "out" / "e2e_platform_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print("ALL PASSED", report["elapsed_s"], "s")
