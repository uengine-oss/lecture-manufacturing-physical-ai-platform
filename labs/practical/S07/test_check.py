"""S07 확인 테스트 — 승인 폼·조치 인자 매핑과 조치 도구 정책 검사.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S07 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S07 -q

DB·Neo4j 에 쓰지 않는다. 프로세스 인스턴스를 시작하지 않는다. 플랫폼(:8910)은 GET 만 호출한다(서버가 없으면 건너뜀).
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b4_ontology.graph import ACTIONS
from labplatform import process

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SYSTEM = HERE.parents[2] / "system"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


policy = _load(BASE / "action_policy.py", f"s07_action_policy_{BASE.name}")
validator = _load(HERE / "validate_mapping.py", "s07_validate_mapping")
DEFN = json.loads((BASE / "process_cooling_response.json").read_text())
ACTS = {a["id"]: a for a in DEFN["activities"]}

# 실제 플랫폼 폐루프 기록(out/e2e_platform_report.json '정상 회복')에서 가져온 사건 맥락
REPORT = json.loads((SYSTEM / "out" / "e2e_platform_report.json").read_text())
PREFILLED = REPORT["cases"][0]["form_prefilled"]
VARS = {
    **PREFILLED,
    "event_type": "COOLING_ANOMALY",
    "citations": [{"doc_id": "SOP-COOL-001", "version": 2, "section": "4"}, {"doc_id": "SOP-LOAD-001", "version": 1, "section": "4"}],
    "rationale": "근거 요약",
    "approval_id": REPORT["golden"]["results"][2]["steps"][1]["sample"][0]["approval_id"],
    "approved_value": 0.8,
    "decision": "APPROVED",
    "approver": "kim.operator",
}


# ---------------------------------------------------------------- 1. 입력 매핑 (정적)
def test_mapping_validator_has_no_problems():
    problems = validator.validate(DEFN)
    assert problems == [], "\n".join(problems)


def test_approval_form_prefills_same_event():
    form = {f["name"]: process.render(f.get("default"), VARS) for f in ACTS["approve"]["fields"]}
    for key in ("event_id", "asset_id", "run_id", "action_id", "proposed_value"):
        assert form.get(key) == PREFILLED[key], f"승인 폼 {key} = {form.get(key)!r}, 기대 {PREFILLED[key]!r}"
    assert form["citations"] == VARS["citations"]


def test_readonly_context_cannot_be_overwritten_on_complete():
    # process.complete() 와 같은 규칙: readonly 가 아닌 필드만 인스턴스 변수에 반영한다
    editable = {f["name"] for f in ACTS["approve"]["fields"] if not f.get("readonly")}
    submitted = {"event_id": "EVT-FORGED", "asset_id": "HYD-02", "run_id": "RUN-x", "proposed_value": 1.0, "citations": [], "decision": "APPROVED", "approved_value": 0.8, "approver": "kim.operator"}
    clean = {k: v for k, v in submitted.items() if k in editable}
    assert set(clean) == {"decision", "approved_value", "approver"}


def test_act_args_pass_approval_id_and_approved_value():
    args = process.render(ACTS["act"]["args"], VARS | {"proposed_value": 0.8, "approved_value": 0.7})
    assert args["event_id"] == PREFILLED["event_id"]
    assert args["approval_id"] == VARS["approval_id"]
    assert args["value"] == 0.7, "조치 값은 사람이 승인한 값이어야 한다"
    assert "approved" not in args, "approved=true 주장은 인자로 넘기지 않는다"


def _next(from_id: str, vars_: dict) -> str | None:
    return next((t["to"] for t in DEFN["transitions"] if t["from"] == from_id and process.cond_ok(t.get("when"), vars_)), None)


@pytest.mark.parametrize(
    "from_id,vars_,expected",
    [
        ("record_evidence", {"event_status": "PENDING_APPROVAL"}, "approve"),
        ("record_evidence", {"event_status": "SENSOR_CHECK"}, "end_hold"),
        ("record_decision", {"decision": "REJECTED", "decision_ok": True}, "end_rejected"),
        ("record_decision", {"decision": "APPROVED", "decision_ok": False}, "end_rejected"),  # 중복 결정 거부
        ("record_decision", {"decision": "APPROVED", "decision_ok": True}, "act"),
        ("act", {"act_ok": False, "refused": "VALUE_OUT_OF_RANGE"}, "end_escalated"),
        ("recheck", {"outcome": "INSUFFICIENT_DATA"}, "end_verify_hold"),
    ],
)
def test_branches(from_id, vars_, expected):
    assert _next(from_id, vars_) == expected


def test_platform_definition_has_same_activities():
    """교육용 플랫폼에 등록된 정의와 활동 구성이 같은지 GET 으로만 대조한다."""
    try:
        r = httpx.get("http://localhost:8910/process/definitions/cooling_response", timeout=3)
    except httpx.HTTPError:
        pytest.skip("교육용 플랫폼(:8910)이 떠 있지 않다")
    if r.status_code != 200:
        pytest.skip("cooling_response 정의가 아직 등록되지 않았다")
    assert [a["id"] for a in r.json()["activities"]] == [a["id"] for a in DEFN["activities"]]


# ---------------------------------------------------------------- 2. 조치 도구 정책 (가짜 저장소)
REDUCE_LOAD = next(a for a in ACTIONS if a["action_id"] == "REDUCE_LOAD")


class FakeRepo:
    def __init__(self, approvals=(), status="PENDING_APPROVAL"):
        self.event = {"event_id": "LAB-EVT-1", "asset_id": "HYD-01", "event_type": "COOLING_ANOMALY", "status": status}
        self.approvals = {a["approval_id"]: a for a in approvals}
        self.logs: list[dict] = []

    def get_event(self, event_id):
        return self.event if event_id == self.event["event_id"] else None

    def get_approval(self, approval_id):
        return self.approvals.get(approval_id)

    def find_action_log(self, key):
        return next((l for l in self.logs if l["idempotency_key"] == key), None)

    def actions_for(self, event_id):
        return [l for l in self.logs if l["event_id"] == event_id]

    def allowed_action(self, asset_id, event_type, action_id):
        return REDUCE_LOAD if (asset_id, event_type, action_id) == ("HYD-01", "COOLING_ANOMALY", "REDUCE_LOAD") else None

    def insert_action_log(self, event_id, approval_id, action_id, value, key, status, detail):
        if self.find_action_log(key):
            return self.find_action_log(key), False
        row = {"action_log_id": f"LAB-ACT-{len(self.logs) + 1}", "event_id": event_id, "approval_id": approval_id, "action_id": action_id, "requested_value": value, "idempotency_key": key, "command_status": status, "command_detail": detail}
        self.logs.append(row)
        return row, True


def approval(decision="APPROVED", value=0.8, action_id="REDUCE_LOAD", event_id="LAB-EVT-1"):
    return {"approval_id": "LAB-APR-1", "event_id": event_id, "decision": decision, "action_id": action_id, "approved_value": value}


def _refused(repo, sim, code, **kw):
    args = {"event_id": "LAB-EVT-1", "approval_id": "LAB-APR-1", "action_id": "REDUCE_LOAD", "value": 0.8} | kw
    with pytest.raises(policy.PolicyError) as e:
        policy.execute_sim_action(repo, sim, **args)
    assert e.value.code == code
    assert repo.logs == [], "거부된 요청은 실행 기록을 남기지 않는다"
    assert sim.state.load == 1.0, "거부된 요청은 시뮬레이터 부하를 바꾸지 않는다"


def test_approved_request_executes_once():
    repo, sim = FakeRepo([approval()]), HydraulicSimulator("HYD-01", seed=42)
    res = policy.execute_sim_action(repo, sim, "LAB-EVT-1", "LAB-APR-1", "REDUCE_LOAD", 0.8)
    assert res["ok"] and not res["duplicate"] and sim.state.load == 0.8
    assert res["action_log"]["approval_id"] == "LAB-APR-1"


def test_llm_claimed_approval_is_refused():
    repo, sim = FakeRepo([]), HydraulicSimulator("HYD-01", seed=42)
    _refused(repo, sim, "APPROVAL_NOT_FOUND", approval_id=None, approved=True)


def test_rejected_approval_is_refused():
    _refused(FakeRepo([approval("REJECTED", None)]), HydraulicSimulator("HYD-01"), "APPROVAL_REJECTED")


def test_value_different_from_approved_is_refused():
    _refused(FakeRepo([approval(value=0.8)]), HydraulicSimulator("HYD-01"), "VALUE_MISMATCH", value=0.7)


def test_out_of_range_is_refused_even_if_approved():
    # 플랫폼 폐루프 '허용 범위 이탈' 사례: 사람이 0.4 를 승인해도 SOP 범위 0.6~1.0 밖이면 실행하지 않는다
    _refused(FakeRepo([approval(value=0.4)]), HydraulicSimulator("HYD-01"), "VALUE_OUT_OF_RANGE", value=0.4)


def test_duplicate_request_returns_existing_record():
    repo, sim = FakeRepo([approval()]), HydraulicSimulator("HYD-01")
    first = policy.execute_sim_action(repo, sim, "LAB-EVT-1", "LAB-APR-1", "REDUCE_LOAD", 0.8)
    sim.state.load = 1.0  # 두 번째 요청이 명령을 다시 보내는지 보기 위해 되돌려 둔다
    second = policy.execute_sim_action(repo, sim, "LAB-EVT-1", "LAB-APR-1", "REDUCE_LOAD", 0.8)
    assert second["duplicate"] and second["action_log"]["action_log_id"] == first["action_log"]["action_log_id"]
    assert len(repo.logs) == 1 and sim.state.load == 1.0


def test_second_attempt_is_repeat_suppressed():
    repo, sim = FakeRepo([approval()]), HydraulicSimulator("HYD-01")
    policy.execute_sim_action(repo, sim, "LAB-EVT-1", "LAB-APR-1", "REDUCE_LOAD", 0.8)
    with pytest.raises(policy.PolicyError) as e:
        policy.execute_sim_action(repo, sim, "LAB-EVT-1", "LAB-APR-1", "REDUCE_LOAD", 0.8, attempt=2)
    assert e.value.code == "REPEAT_SUPPRESSED" and len(repo.logs) == 1
