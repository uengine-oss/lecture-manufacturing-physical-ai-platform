"""실라버스 '공통 데모 사례'와 '상태 흐름'의 분기를 끝까지 실행해 확인한다."""
import pytest

from hydops.b1_data import inspection
from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b3_tsdb import store
from hydops.b5_detect.product import check_lots
from hydops.b8_action import executor
from tests.helpers import run_until_settled, tick_until_event


def degrade_and_detect(rt, orc, cooling=0.4):
    rt.tick(30)
    rt.sims["HYD-01"].inject_cooling_degradation(cooling)
    ev = tick_until_event(rt, "COOLING_ANOMALY")
    assert ev, "냉각 이상 사건이 생성되어야 한다"
    orc.start(ev["event_id"])
    assert store.get_event(ev["event_id"])["status"] == "PENDING_APPROVAL"
    return ev


def test_normal_operation_no_action(plant):
    rt, orc = plant
    assert rt.tick(120) == []
    assert store.list_events(run_id=rt.run_id) == []


def test_single_spike_is_not_an_event(plant):
    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-01"].inject_sensor_fault("spike", seconds=3)
    assert rt.tick(40) == []


def test_sensor_fault_holds_equipment_action(plant):
    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-01"].inject_sensor_fault("dropout", seconds=20)
    ev = tick_until_event(rt, "SENSOR_FAULT", max_s=30)
    assert ev is not None
    orc.start(ev["event_id"])
    e = store.get_event(ev["event_id"])
    assert e["status"] == "SENSOR_CHECK"
    assert store.actions_for(ev["event_id"]) == []  # 설비 조치 없음
    assert rt.sims["HYD-01"].state.load == 1.0
    cits = e["proposal"]["proposal"]["citations"]
    assert cits and all(c["doc_id"] == "SOP-SEN-001" for c in cits)


def test_stuck_sensor_is_sensor_fault_not_equipment(plant):
    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-01"].inject_sensor_fault("stuck", seconds=15)
    ev = tick_until_event(rt, max_s=30)
    assert ev["event_type"] == "SENSOR_FAULT"


def test_cooling_degradation_recovers_and_closes(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc, 0.4)
    eid = ev["event_id"]
    r = orc.decide(eid, "kim.operator", "APPROVED", 0.8)
    assert r["ok"]
    assert rt.sims["HYD-01"].state.load == 0.8
    assert run_until_settled(rt, orc, eid) == "CLOSED"
    trace = store.event_trace(eid)
    assert trace["actions"][0]["command_status"] == "SUCCEEDED"
    assert trace["verifications"][0]["outcome"] == "RECOVERED"
    # 재측정은 조치 이후의 관측만 참조한다
    assert trace["verifications"][0]["window_start"] > trace["actions"][0]["sim_ts"]


def test_not_improved_is_escalated_and_not_repeated(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc, 0.25)
    eid = ev["event_id"]
    orc.decide(eid, "kim.operator", "APPROVED", 0.8)
    assert run_until_settled(rt, orc, eid) == "ESCALATED"
    trace = store.event_trace(eid)
    assert trace["actions"][0]["command_status"] == "SUCCEEDED"  # 명령은 성공
    assert trace["verifications"][0]["outcome"] == "NOT_IMPROVED"  # 회복은 실패
    assert len(trace["actions"]) == 1
    # 같은 사건에 다시 제안 검사를 해도 반복 조치는 막힌다
    chk = executor.propose_action(eid, "REDUCE_LOAD", 0.8, [{"doc_id": "SOP-LOAD-001", "version": 1, "section": "4"}])
    assert not chk["ok"]


def test_rejection_ends_without_execution(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    orc.decide(ev["event_id"], "kim.operator", "REJECTED", None, "현장 확인 우선")
    assert store.get_event(ev["event_id"])["status"] == "REJECTED"
    assert store.actions_for(ev["event_id"]) == []
    assert rt.sims["HYD-01"].state.load == 1.0


def test_duplicate_approval_request_is_refused(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    assert orc.decide(ev["event_id"], "kim.operator", "APPROVED", 0.8)["ok"]
    dup = orc.decide(ev["event_id"], "kim.operator", "APPROVED", 0.8)
    assert not dup["ok"] and dup["error"] == "NOT_WAITING_FOR_APPROVAL"
    assert len(store.actions_for(ev["event_id"])) == 1


def test_llm_claimed_approval_is_not_accepted(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    with pytest.raises(executor.PolicyError) as e:
        executor.execute_sim_action(rt.sims["HYD-01"], ev["event_id"], None, "REDUCE_LOAD", 0.8, approved=True)
    assert e.value.code == "APPROVAL_NOT_FOUND"
    assert rt.sims["HYD-01"].state.load == 1.0


def test_out_of_range_value_is_refused_by_tool(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    orc.decide(ev["event_id"], "kim.operator", "APPROVED", 0.4)  # 허용 범위 0.6~1.0 이탈
    e = store.get_event(ev["event_id"])
    assert e["status"] == "ESCALATED" and "VALUE_OUT_OF_RANGE" in e["status_reason"]
    assert rt.sims["HYD-01"].state.load == 1.0


def test_command_failure_is_escalated(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    rt.sims["HYD-01"].fail_next_command()
    orc.decide(ev["event_id"], "kim.operator", "APPROVED", 0.8)
    e = store.get_event(ev["event_id"])
    assert e["status"] == "ESCALATED"
    assert store.actions_for(ev["event_id"])[0]["command_status"] == "FAILED"


def test_insufficient_data_holds_then_remeasures(plant):
    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    eid = ev["event_id"]
    orc.decide(eid, "kim.operator", "APPROVED", 0.8)
    rt.tick(28)
    rt.sims["HYD-01"].inject_sensor_fault("dropout", seconds=45)  # 첫 재측정 창의 대부분이 결측
    status = run_until_settled(rt, orc, eid, max_s=260)
    vers = store.verifications_for(eid)
    assert vers[0]["outcome"] == "INSUFFICIENT_DATA"
    assert status == "CLOSED" and vers[-1]["outcome"] == "RECOVERED"


def test_restart_does_not_repeat_action(plant):
    from hydops.b8_action.workflow import Orchestrator

    rt, orc = plant
    ev = degrade_and_detect(rt, orc)
    eid = ev["event_id"]
    r = orc.decide(eid, "kim.operator", "APPROVED", 0.8)
    orc.close()
    orc2 = Orchestrator(rt, agent_mode="offline")  # 재시작
    try:
        again = orc2.start(eid)
        assert again["started"] is False
        apr = store.approvals_for(eid)[0]
        store.transition(eid, "PENDING_APPROVAL", "test", {"note": "재시작 후 같은 요청 재전송 모사"})
        res = executor.execute_sim_action(rt.sims["HYD-01"], eid, apr["approval_id"], "REDUCE_LOAD", 0.8)
        assert res["duplicate"] is True
        assert len(store.actions_for(eid)) == 1
    finally:
        orc2.close()
        orc.pool = orc2.pool  # fixture 정리용


def test_no_evidence_is_hold(plant):
    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-03"].inject_cooling_degradation(0.4)  # 3호기(신규): 적용 SOP 가 등록되지 않았다
    ev = tick_until_event(rt, "COOLING_ANOMALY", asset_id="HYD-03")
    orc.start(ev["event_id"])
    assert store.get_event(ev["event_id"])["status"] == "HOLD_NO_EVIDENCE"
    assert store.actions_for(ev["event_id"]) == []


def test_other_asset_gets_its_own_sop_action(plant):
    """2호기는 자기 SOP(SOP-COOL-002)의 팬 증속을 제안받고, 1호기의 부하 감소가 섞이지 않는다."""
    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-02"].inject_cooling_degradation(0.4)
    ev = tick_until_event(rt, "COOLING_ANOMALY", asset_id="HYD-02")
    orc.start(ev["event_id"])
    e = store.get_event(ev["event_id"])
    p = e["proposal"]["proposal"]
    assert e["status"] == "PENDING_APPROVAL" and p["action_id"] == "FAN_BOOST"
    assert all(c["doc_id"] != "SOP-COOL-001" and c["doc_id"] != "SOP-LOAD-001" for c in p["citations"])
    orc.decide(ev["event_id"], "lee.operator", "APPROVED", p["value"])
    assert run_until_settled(rt, orc, ev["event_id"]) == "CLOSED"


def test_fabricated_citation_is_hold():
    from hydops.b7_agent.agent import Proposal, verify_citations

    p = Proposal(decision="PROPOSE", action_id="REDUCE_LOAD", value=0.8, citations=[{"doc_id": "SOP-FAKE-9", "version": 1, "section": "4"}], rationale="x")
    trace = [{"tool": "search_sop", "result": {"hits": [{"doc_id": "SOP-LOAD-001", "version": 1, "section": "4"}]}}]
    final, problems = verify_citations(p, trace)
    assert final.decision == "HOLD" and problems == ["SOP-FAKE-9@v1#4"]


def test_product_quality_is_separate_event(plant):
    rt, orc = plant
    rows = inspection.synth_lots("HYD-01", rt.now())
    store.insert_inspections(rt.run_id, rows)
    evs = check_lots(rt.run_id, rows)
    assert evs and all(e["event_type"] == "PRODUCT_QUALITY" for e in evs)
    assert store.open_event("HYD-01", "COOLING_ANOMALY") is None


def test_same_seed_with_and_without_action():
    a, b = HydraulicSimulator(seed=7), HydraulicSimulator(seed=7)
    for s in (a, b):
        s.run(20)
        s.inject_cooling_degradation(0.4)
        s.run(60)
    a.apply_load(0.8)
    ta = [r["raw_value"] for r in a.run(90) if r["sensor_id"] == "TS1"]
    tb = [r["raw_value"] for r in b.run(90) if r["sensor_id"] == "TS1"]
    assert max(ta[-20:]) <= 55.0 < min(tb[-20:])


def test_earlier_sensor_gap_does_not_block_real_cooling_anomaly(plant):
    """센서 결측이 끝난 뒤 생긴 실제 냉각 이상은 센서 오류로 오판하지 않는다 (영상 리허설에서 발견)."""
    rt, orc = plant
    rt.tick(10)
    rt.sims["HYD-01"].inject_sensor_fault("dropout", seconds=20)
    sf = tick_until_event(rt, "SENSOR_FAULT", max_s=30)
    orc.start(sf["event_id"])
    rt.tick(12)  # 센서 복구
    rt.sims["HYD-01"].inject_cooling_degradation(0.4)
    ev = tick_until_event(rt, "COOLING_ANOMALY")
    orc.start(ev["event_id"])
    e = store.get_event(ev["event_id"])
    assert e["status"] == "PENDING_APPROVAL", e["status_reason"]
    ts = next(t for t in e["proposal"]["tool_trace"] if t["tool"] == "get_recent_window")["result_summary"]
    assert ts["sensor_state"] == "VALID"
