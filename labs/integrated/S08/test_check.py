"""통합반 8회 실습 검사 — 기본은 학생 파일, LAB_SOLUTION=1 이면 solution/ 을 검사한다.

학생 산출물(에이전트 할당 JSON·프로세스 입력 매핑)을 정적으로 검사하고,
교육용 플랫폼(:8910)에는 GET 만 호출해 등록된 Skill·MCP 도구·프로세스 정의·인스턴스와 대조한다.
프로세스 시작·태스크 완료는 하지 않는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest
import yaml

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SYSTEM = HERE.parents[2] / "system"
T = SYSTEM / "labplatform" / "templates"
PROCESS_TPL = json.loads((T / "process_cooling_response.json").read_text())
WATCH_TPL = json.loads((T / "watch_events.json").read_text())
SKILL_MD = (SYSTEM / "skills" / "hydraulic-cooling-response" / "SKILL.md").read_text()
PLATFORM = "http://localhost:8910"
EXECUTE_TOOLS = {"execute_sim_action", "verify_recovery"}


def up() -> bool:
    try:
        return httpx.get(f"{PLATFORM}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


needs_platform = pytest.mark.skipif(not up(), reason="교육용 플랫폼(:8910)이 꺼져 있다")


def assignment() -> dict:
    return json.loads((SRC / "agent_assignment.json").read_text())


def mapping() -> dict:
    return json.loads((SRC / "process_mapping.json").read_text())


def activity(aid: str) -> dict:
    return next(a for a in PROCESS_TPL["activities"] if a["id"] == aid)


def skill_meta() -> dict:
    return yaml.safe_load(SKILL_MD.split("---", 2)[1])


# ---- 1. 빈칸 ---------------------------------------------------------------------
def test_no_blanks_left():
    for f in ("agent_assignment.json", "process_mapping.json"):
        assert "____" not in (SRC / f).read_text(), f"{f} 에 빈칸(____)이 남아 있다"


# ---- 2. 에이전트 할당 (정적) ----------------------------------------------------------
def test_agent_uses_skill_and_query_tools_only():
    a = assignment()
    meta = skill_meta()
    assert a["skills"] == [meta["name"]], "할당할 Skill 이름은 SKILL.md frontmatter 의 name 이다"
    assert a["mcp_servers"] == ["hydops"]
    assert len(set(a["allowed_tools"])) == len(a["allowed_tools"]), "허용 도구가 중복됐다"
    assert not (set(a["allowed_tools"]) & EXECUTE_TOOLS), "업무 에이전트에 실행·재측정 도구를 허용하면 안 된다 — 실행은 승인 뒤 프로세스의 도구 활동이 한다"
    assert set(a["allowed_tools"]) == set(meta["tools"]), "허용 도구는 Skill 이 쓰는 조회·검색·제안 도구 4종과 같아야 한다"


# ---- 3. 프로세스 입력 매핑 (정적) -------------------------------------------------------
def test_intake_and_watch_mapping():
    m = mapping()
    assert m["def_id"] == PROCESS_TPL["def_id"]
    assert m["instance_key"] == PROCESS_TPL["instance_key"], "중복 시작을 막는 인스턴스 키 필드"
    assert m["watch_param_map"] == WATCH_TPL["param_map"]
    required = [f["name"] for f in activity("intake")["fields"] if f.get("required")]
    assert sorted(m["intake_required_fields"]) == sorted(required)


def test_approve_form_mapping():
    m = mapping()["approve_form"]
    act = activity("approve")
    fields = {f["name"]: f for f in act["fields"]}
    assert m["role"] == act["role"]
    for name, tpl in m["readonly_defaults"].items():
        assert fields[name].get("readonly") and fields[name]["default"] == tpl, f"승인 폼 {name} 의 기본값 매핑이 틀렸다"
    assert set(m["readonly_defaults"]) == {"event_id", "asset_id", "run_id", "action_id", "proposed_value", "citations"}
    assert m["decision_options"] == fields["decision"]["options"]
    assert m["approved_value_default"] == fields["approved_value"]["default"]


def test_action_runs_with_approved_value_and_approval_id():
    m = mapping()
    assert m["record_decision_body"] == {k: v for k, v in activity("record_decision")["body"].items() if k != "comment"}
    act = activity("act")
    assert m["act"]["tool"] == act["tool"] and m["act"]["tool"] in EXECUTE_TOOLS
    assert m["act"]["args"] == act["args"]
    assert m["act"]["args"]["value"] == "${approved_value}", "조치는 제안값이 아니라 사람이 승인한 값으로 실행한다"
    gate = next(t for t in PROCESS_TPL["transitions"] if t["from"] == "record_decision" and t["to"] == "act")
    assert {"var": "decision", "op": "==", "value": m["to_act_when_decision"]} in gate["when"]["all"]


def test_mapping_renders_with_engine_function():
    """교육용 플랫폼 엔진의 실제 치환 함수(labplatform.process.render)로 매핑을 채워 본다."""
    from labplatform.process import render

    m = mapping()
    vars_ = {"event_id": "EVT-X", "asset_id": "HYD-01", "run_id": "RUN-X", "action_id": "REDUCE_LOAD", "proposed_value": 0.8, "citations": [{"doc_id": "SOP-LOAD-001", "version": 1, "section": "4"}], "approval_id": "APR-X", "approved_value": 0.8}
    form = render(m["approve_form"]["readonly_defaults"], vars_)
    assert form["event_id"] == "EVT-X" and form["asset_id"] == "HYD-01" and form["proposed_value"] == 0.8
    assert render(m["act"]["args"], vars_) == {"event_id": "EVT-X", "approval_id": "APR-X", "action_id": "REDUCE_LOAD", "value": 0.8}


# ---- 4. 등록된 플랫폼 상태와 대조 (GET) --------------------------------------------------
@needs_platform
def test_assignment_matches_registered_skill_and_tools():
    a = assignment()
    skills = {s["name"] for s in httpx.get(f"{PLATFORM}/agents/skills", timeout=10).json()}
    assert set(a["skills"]) <= skills, f"사전 등록된 Skill 은 {sorted(skills)}"
    servers = {s["name"] for s in httpx.get(f"{PLATFORM}/agents/mcp-servers", timeout=10).json()}
    assert set(a["mcp_servers"]) <= servers
    tools = {t["name"] for t in httpx.get(f"{PLATFORM}/agents/mcp-servers/hydops/tools", timeout=30).json()}
    assert set(a["allowed_tools"]) <= tools
    assert EXECUTE_TOOLS <= tools, "실행 도구는 서버에 있지만 에이전트에는 허용하지 않는다"


@needs_platform
def test_mapping_matches_registered_definition():
    r = httpx.get(f"{PLATFORM}/process/definitions/{mapping()['def_id']}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    appr = next(a for a in d["activities"] if a["id"] == "approve")
    defaults = {f["name"]: f.get("default") for f in appr["fields"]}
    for k, v in mapping()["approve_form"]["readonly_defaults"].items():
        assert defaults[k] == v


@needs_platform
def test_event_id_preserved_in_real_instance():
    """완료된 실제 인스턴스가 있으면: 매핑을 인스턴스 변수로 채운 값 == 승인 폼·실행 도구 입력에 남은 값."""
    from labplatform.process import render

    insts = httpx.get(f"{PLATFORM}/process/instances", timeout=10).json()
    checked = 0
    for row in insts:
        inst = httpx.get(f"{PLATFORM}/process/instances/{row['instance_id']}", timeout=10).json()
        steps = {s["activity_id"]: s for s in inst["steps"]}
        if "approve" not in steps or "act" not in steps or steps["approve"]["status"] != "DONE":
            continue
        form = {f["name"]: f.get("value") for f in steps["approve"]["form"]}
        rendered = render(mapping()["approve_form"]["readonly_defaults"], inst["vars"])
        for k in ("event_id", "asset_id", "run_id", "action_id", "proposed_value"):
            assert rendered[k] == form[k], f"{row['instance_id']} 승인 폼 {k}"
        assert steps["intake"]["input"]["event_id"] == form["event_id"] == steps["act"]["input"]["args"]["event_id"]
        checked += 1
    if not checked:
        pytest.skip("승인·실행까지 진행된 인스턴스가 아직 없다")
