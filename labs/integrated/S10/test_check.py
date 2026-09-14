"""통합반 10회 실습 검사 — 기본은 학생 check_submission.py, LAB_SOLUTION=1 이면 solution/ 을 검사한다.

fixtures/ 는 2026-09-14 실제 시스템에서 GET /api/events/{id} 로 받은 기록이다.
- event_closed_f81e.json   : 교육용 플랫폼 프로세스로 처리된 정상 회복 사건 (PI-75788b6a)
- event_rejected_61ac.json : 승인 거부 사건 (실행 기록 0)
위반 사례는 이 실제 기록을 한 곳씩 바꿔 만든다. 관제 API(:8800)에는 GET 만 호출한다.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
FIX = HERE / "fixtures"
HYDOPS = "http://localhost:8800"


def load():
    spec = importlib.util.spec_from_file_location("s10_check_submission", SRC / "check_submission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def closed() -> dict:
    return json.loads((FIX / "event_closed_f81e.json").read_text())


def rejected() -> dict:
    return json.loads((FIX / "event_rejected_61ac.json").read_text())


def up() -> bool:
    try:
        return httpx.get(f"{HYDOPS}/api/state", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


def rule(mod, d, name):
    return mod.check(d)["rules"][name]["ok"]


EVID, APPR, DUP, VERI = "근거 없는 조치 0건", "승인 없는 실행 0건", "중복 실행 0건", "재측정 없는 회복 판정 0건"


# ---- 1. 빈칸 ---------------------------------------------------------------------
def test_no_blanks_left():
    body = (SRC / "check_submission.py").read_text().replace("____ = None", "")
    assert "____" not in body, "check_submission.py 에 빈칸(____)이 남아 있다"


# ---- 2. 실제 기록은 통과한다 -----------------------------------------------------------
def test_recorded_closed_event_passes_all_four():
    res = load().check(closed())
    assert res["passed"], res
    assert res["status"] == "CLOSED"


def test_recorded_rejected_event_passes_without_actions():
    res = load().check(rejected())
    assert res["passed"], res
    assert res["rules"][APPR]["message"].endswith("실행 0건")


# ---- 3. 한 곳만 바꾼 위반 사례는 걸린다 ---------------------------------------------------
def test_action_without_evidence_is_flagged():
    m = load()
    d = closed()
    d["event"]["proposal"]["proposal"]["citations"] = []
    assert not rule(m, d, EVID)
    d = closed()
    d["event"]["proposal"]["proposal"]["citations"][0]["section"] = "9"  # 그래프에 없는 절
    assert not rule(m, d, EVID)
    d = closed()
    d["event"]["proposal"]["citation_problems"] = ["검색되지 않은 인용"]
    assert not rule(m, d, EVID)


def test_action_without_valid_approval_is_flagged():
    m = load()
    d = closed()
    d["approvals"] = []
    assert not rule(m, d, APPR)
    d = closed()
    d["approvals"][0]["decision"] = "REJECTED"
    assert not rule(m, d, APPR)
    d = closed()
    d["approvals"][0]["decided_at"] = "2026-09-14T13:10:40+00:00"  # 실행(13:10:32.66) 뒤의 승인
    assert not rule(m, d, APPR)
    d = closed()
    d["actions"][0]["requested_value"] = 0.4  # 승인값 0.8 과 다른 실행값
    assert not rule(m, d, APPR)
    d = rejected()
    d["actions"] = copy.deepcopy(closed()["actions"])
    assert not rule(m, d, APPR)


def test_duplicate_execution_is_flagged():
    m = load()
    d = closed()
    d["actions"].append(copy.deepcopy(d["actions"][0]))  # 같은 중복 방지 키
    assert not rule(m, d, DUP)
    d = closed()
    second = copy.deepcopy(d["actions"][0])
    second.update(action_log_id="ACT-second", idempotency_key=second["idempotency_key"].replace(":1", ":2"))
    d["actions"].append(second)  # 키는 달라도 성공한 조치가 두 번
    assert not rule(m, d, DUP)


def test_recovery_without_remeasure_is_flagged():
    m = load()
    d = closed()
    d["verifications"] = []
    assert not rule(m, d, VERI)
    d = closed()
    d["verifications"][0]["outcome"] = "NOT_IMPROVED"
    assert not rule(m, d, VERI)
    d = closed()
    d["verifications"][0]["window_start"] = "2026-09-14T13:12:00+00:00"  # 조치 시각(13:12:22) 이전 관측
    assert not rule(m, d, VERI)
    d = closed()
    for h in d["history"]:
        if h["to_status"] == "CLOSED":
            h["actor"] = "executor"  # 명령 성공만으로 종결
    assert not rule(m, d, VERI)


def test_record_keeps_same_event_id_in_four_sections():
    m = load()
    d = closed()
    rec = m.build_record(d)
    eid = d["event"]["event_id"]
    for sec in ("감지", "근거", "조치", "재측정"):
        assert rec[sec]["event_id"] == eid
    assert all(a["event_id"] == eid for a in rec["조치"]["actions"] + rec["조치"]["approvals"])
    assert all(v["event_id"] == eid for v in rec["재측정"]["verifications"])
    assert rec["업무"]["instance_id"] == "PI-75788b6a"
    md = m.to_markdown(d)
    assert md.count("| 통과 |") == 4


# ---- 4. 실제 시스템의 사건 전체 (GET) ------------------------------------------------------
@pytest.mark.skipif(not up(), reason="관제 API(:8800)가 꺼져 있다")
def test_all_recorded_events_meet_zero_goals():
    m = load()
    ids = m.list_event_ids()
    if not ids:
        pytest.skip("기록된 사건이 없다")
    failed = []
    for eid in ids:
        res = m.check(m.fetch_detail(eid))
        if not res["passed"]:
            failed.append(res)
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
