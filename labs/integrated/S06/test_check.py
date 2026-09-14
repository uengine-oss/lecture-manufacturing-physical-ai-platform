"""통합반 S06 점검 — 에이전트 도구 연결, 모의 승인 버튼, 거부·실패·재조회 상태표.

실행: cd lecture/system && HYDOPS_AGENT_MODE=offline PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S06 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
공유 DB·Neo4j·서버에 쓰지 않는다: 실제 hydops 코드(run_offline_agent, verify_citations, executor, service)를
lab_fakes.py 의 메모리 저장소에 연결해 돌린다 (run_id LAB-S06).
"""
import importlib.util
import inspect
import os
import re
import sys
from pathlib import Path

import pytest

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b7_agent import agent
from hydops.b7_agent.agent import Proposal, verify_citations
from hydops.b8_action import executor, service
from hydops.config import ROOT

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
sys.path.insert(0, str(HERE))


def _load(name, base=SRC):
    spec = importlib.util.spec_from_file_location(f"s06_{name}_{id(base)}", base / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fakes = _load("lab_fakes", HERE)
lab_agent = _load("lab_agent")
wiring = _load("approval_wiring")
table = _load("state_table")


# ---- 사건 준비 ---------------------------------------------------------------------------
def prepare(monkeypatch, asset_id="HYD-01", kind="cooling", eff=0.4, executed_before=False):
    plant = fakes.LabPlant()
    fakes.patch_system(monkeypatch, plant)
    plant.tick(30)
    sim = plant.sims[asset_id]
    if kind == "cooling":
        sim.inject_cooling_degradation(eff)
        plant.tick(40)
        et = "COOLING_ANOMALY"
    else:
        sim.inject_sensor_fault("dropout", 20)
        plant.tick(12)
        et = "SENSOR_FAULT"
    ev = plant.store.add_event(asset_id, et, sim.state.t)
    if executed_before:
        plant.store.insert_action_log(ev["event_id"], None, "REDUCE_LOAD", 0.8, f"{ev['event_id']}:REDUCE_LOAD:1", "SUCCEEDED", {})
    return plant, ev


# ---- 1. 도구 연결: 학생 에이전트 = 제공 오프라인 에이전트 ----------------------------------------
AGENT_CASES = [
    ("HYD-01", "cooling", False, "PROPOSE", "REDUCE_LOAD", 0.8),
    ("HYD-01", "dropout", False, "SENSOR_CHECK", "SENSOR_CHECK", None),
    ("HYD-02", "cooling", False, "PROPOSE", "FAN_BOOST", 1.3),
    ("HYD-03", "cooling", False, "HOLD", None, None),
    ("HYD-01", "cooling", True, "ESCALATE", "REDUCE_LOAD", 0.8),
]


@pytest.mark.parametrize("asset_id,kind,executed,decision,action_id,value", AGENT_CASES)
def test_lab_agent_matches_offline_agent(monkeypatch, asset_id, kind, executed, decision, action_id, value):
    plant, ev = prepare(monkeypatch, asset_id, kind, executed_before=executed)
    real_trace, lab_trace = [], []
    real = agent.run_offline_agent(ev, real_trace)
    mine = lab_agent.run_lab_agent(ev, fakes.make_tools(plant, lab_trace))

    assert (real.decision, real.action_id, real.value) == (decision, action_id, value)
    assert (mine["decision"], mine["action_id"], mine["value"]) == (decision, action_id, value)
    assert mine["citations"] == [c.model_dump() for c in real.citations]
    assert [t["tool"] for t in lab_trace] == [t["tool"] for t in real_trace], "도구 호출 순서가 제공 에이전트와 달라졌다"
    # 근거 검증을 통과해야 한다 (인용이 이번 검색 결과에 있다)
    final, problems = verify_citations(Proposal(**mine), lab_trace)
    assert final.decision == decision and problems == []
    # 승인 전 미실행: 에이전트는 실행 도구를 부르지 않는다
    assert {t["tool"] for t in lab_trace} <= {"get_recent_window", "get_asset_context", "search_sop", "propose_action"}
    assert all(s.state.load == 1.0 for s in plant.sims.values())
    assert len(plant.store.actions) == (1 if executed else 0)


def test_sensor_state_is_checked_first(monkeypatch):
    plant, ev = prepare(monkeypatch, "HYD-01", "dropout")
    trace = []
    lab_agent.run_lab_agent(ev, fakes.make_tools(plant, trace))
    assert trace[0]["tool"] == "get_recent_window"
    assert [t["args"].get("event_type") for t in trace if t["tool"] == "search_sop"] == ["SENSOR_FAULT"]


# ---- 2. 모의 승인 버튼 ----------------------------------------------------------------------
def test_decision_route_matches_dashboard():
    app_py = (ROOT / "hydops" / "b9_dashboard" / "app.py").read_text()
    app_js = (ROOT / "hydops" / "b9_dashboard" / "static" / "app.js").read_text()
    assert f'@app.post("{wiring.DECISION_PATH}")' in app_py
    assert "'/decision'" in app_js and wiring.DECISION_PATH.endswith("/decision")


def test_decision_body():
    assert wiring.decision_body("승인", "kim.operator", 0.8) == {"approver": "kim.operator", "decision": "APPROVED", "value": 0.8}
    assert wiring.decision_body("거부", "kim.operator", 0.8) == {"approver": "kim.operator", "decision": "REJECTED", "value": None}
    app_js = (ROOT / "hydops" / "b9_dashboard" / "static" / "app.js").read_text()
    assert "value: decision === 'APPROVED' ? this.approveValue : null" in app_js


def test_action_to_simulator_method():
    src = inspect.getsource(executor.execute_sim_action)
    for action_id, method in wiring.ACTION_TO_METHOD.items():
        assert hasattr(HydraulicSimulator, method)
        assert f'"{action_id}": sim.{method}' in src


@pytest.mark.parametrize("button,expected_load,expected_status", [("승인", 0.8, "VERIFYING"), ("거부", 1.0, "REJECTED")])
def test_button_flow_runs_real_service(monkeypatch, button, expected_load, expected_status):
    plant, ev = prepare(monkeypatch)
    eid, sim = ev["event_id"], plant.sims["HYD-01"]
    service.gather_evidence(eid, "offline")
    assert plant.store.get_event(eid)["status"] == "PENDING_APPROVAL" and sim.state.load == 1.0  # 승인 전 미실행
    body = wiring.decision_body(button, "kim.operator", 0.8)
    rec = service.record_decision(eid, body["approver"], body["decision"], body["value"])
    assert rec["ok"]
    if body["decision"] == "APPROVED":
        method = wiring.ACTION_TO_METHOD[plant.store.get_event(eid)["proposal"]["proposal"]["action_id"]]
        assert method == "apply_load"
        service.execute(sim, eid, rec["approval"]["approval_id"], "REDUCE_LOAD", body["value"])
    assert sim.state.load == expected_load
    assert plant.store.get_event(eid)["status"] == expected_status


# ---- 3. 상태표: 실제 service 로 각 상황을 끝까지 돌린다 ----------------------------------------------
def outcome(plant, eid, error=None):
    return {"status": plant.store.get_event(eid)["status"], "action_logs": len(plant.store.actions_for(eid)), "error": error}


def approved(monkeypatch, value=0.8, eff=0.4, fail=False):
    plant, ev = prepare(monkeypatch, eff=eff)
    eid, sim = ev["event_id"], plant.sims["HYD-01"]
    service.gather_evidence(eid, "offline")
    rec = service.record_decision(eid, "kim.operator", "APPROVED", value)
    if fail:
        sim.fail_next_command()
    res = service.execute(sim, eid, rec["approval"]["approval_id"], "REDUCE_LOAD", value)
    return plant, eid, sim, res


def run_scenario(monkeypatch, name):
    if name == "proposed":
        plant, ev = prepare(monkeypatch)
        service.gather_evidence(ev["event_id"], "offline")
        return outcome(plant, ev["event_id"])
    if name == "rejected":
        plant, ev = prepare(monkeypatch)
        service.gather_evidence(ev["event_id"], "offline")
        service.record_decision(ev["event_id"], "kim.operator", "REJECTED", None, "현장 확인 우선")
        return outcome(plant, ev["event_id"])
    if name == "approved_executed":
        plant, eid, _, _ = approved(monkeypatch)
        return outcome(plant, eid)
    if name in ("recovered", "not_improved"):
        plant, eid, _, res = approved(monkeypatch, eff=0.4 if name == "recovered" else 0.25)
        plant.tick(100)
        service.verify(eid, res["action_log"]["action_log_id"], 0)
        return outcome(plant, eid)
    if name == "command_failed":
        plant, eid, _, res = approved(monkeypatch, fail=True)
        assert plant.store.actions_for(eid)[0]["command_status"] == "FAILED"
        return outcome(plant, eid)
    if name == "out_of_range":
        plant, eid, _, res = approved(monkeypatch, value=0.4)
        return outcome(plant, eid, res.get("refused"))
    if name == "no_approval_record":
        plant, ev = prepare(monkeypatch)
        eid = ev["event_id"]
        service.gather_evidence(eid, "offline")
        res = service.execute(plant.sims["HYD-01"], eid, None, "REDUCE_LOAD", 0.8, approved=True)
        return outcome(plant, eid, res.get("refused"))
    if name == "duplicate_decision":
        plant, eid, _, _ = approved(monkeypatch)
        rec = service.record_decision(eid, "kim.operator", "APPROVED", 0.8)
        return outcome(plant, eid, rec.get("error"))
    if name in ("insufficient_first", "insufficient_then_recovered"):
        plant, eid, sim, res = approved(monkeypatch)
        plant.tick(28)
        sim.inject_sensor_fault("dropout", 45)  # 첫 재측정 창 대부분이 결측
        plant.tick(62)
        first = service.verify(eid, res["action_log"]["action_log_id"], 0)
        assert first["outcome"] == "INSUFFICIENT_DATA" and first["next_window_index"] == 1
        if name == "insufficient_then_recovered":
            plant.tick(60)
            service.verify(eid, res["action_log"]["action_log_id"], 1)
        return outcome(plant, eid)
    raise KeyError(name)


SCENARIOS = ["proposed", "rejected", "approved_executed", "recovered", "not_improved", "command_failed", "out_of_range",
             "no_approval_record", "duplicate_decision", "insufficient_first", "insufficient_then_recovered"]


def test_table_has_all_rows():
    assert list(table.STATE_TABLE) == SCENARIOS


@pytest.mark.parametrize("name", SCENARIOS)
def test_state_table_matches_service(monkeypatch, name):
    expected = table.STATE_TABLE[name]
    assert "____" not in map(str, expected.values()), f"{name} 행에 빈칸이 남아 있다"
    assert run_scenario(monkeypatch, name) == expected


def test_command_success_is_not_recovery(monkeypatch):
    # 미개선 사례: 명령은 SUCCEEDED, 재측정은 NOT_IMPROVED — 두 기록은 따로 남는다
    plant, eid, _, res = approved(monkeypatch, eff=0.25)
    plant.tick(100)
    service.verify(eid, res["action_log"]["action_log_id"], 0)
    assert plant.store.actions_for(eid)[0]["command_status"] == "SUCCEEDED"
    assert plant.store.verifications[-1]["outcome"] == "NOT_IMPROVED"
    assert re.search("미개선", plant.store.get_event(eid)["status_reason"])
