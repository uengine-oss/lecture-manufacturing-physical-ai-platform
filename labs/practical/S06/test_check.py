"""실전반 S06 확인 테스트 — 플랫폼 어댑터(PlatformContext)와 로컬·플랫폼 맥락 대조.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S06 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S06 -q

1부: 가짜 플랫폼 응답(httpx.MockTransport)으로 어댑터 논리를 검사한다 — 서버가 없어도 돈다.
2부: 실행 중인 교육용 플랫폼(:8910)의 발행된 HydraulicOps 를 읽기 전용으로 조회한다
     (objects/fetch · related · behaviors/invoke). 발행·가져오기·바인딩 변경은 하지 않는다. 서버가 없으면 건너뛴다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

os.environ.setdefault("HYDOPS_AGENT_MODE", "offline")

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
PLATFORM = os.environ.get("LAB_PLATFORM_URL", "http://localhost:8910")


def _load(name: str):
    mod_name = f"lab_s06_{name}_{'solution' if BASE.name == 'solution' else 'student'}"
    spec = importlib.util.spec_from_file_location(mod_name, BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


P = _load("platform_adapter")

# ---- 1부: 가짜 플랫폼 (실제 응답 모양을 줄여 옮김) -----------------------------------------
ASSETS = {"HYD-01": {"asset_id": "HYD-01", "name": "유압설비 1호기", "cooling": "수랭식 냉각기", "line": "L1"},
          "HYD-02": {"asset_id": "HYD-02", "name": "유압설비 2호기", "cooling": "공랭식 팬", "line": "L2"}}
SOPS = {
    "SOP-COOL-001@v2": {"doc_id": "SOP-COOL-001", "version": 2, "title": "냉각 이상 확인", "status": "active", "event_type": "COOLING_ANOMALY", "assets": ["HYD-01"], "allows": ["REDUCE_LOAD"]},
    "SOP-COOL-002@v1": {"doc_id": "SOP-COOL-002", "version": 1, "title": "냉각 이상 확인 (2호기 공랭식)", "status": "active", "event_type": "COOLING_ANOMALY", "assets": ["HYD-02"], "allows": ["FAN_BOOST"]},
    "SOP-LOAD-001@v1": {"doc_id": "SOP-LOAD-001", "version": 1, "title": "승인 부하 감소", "status": "active", "event_type": "COOLING_ANOMALY", "assets": ["HYD-01"], "allows": ["REDUCE_LOAD"]},
    "SOP-ESC-001@v1": {"doc_id": "SOP-ESC-001", "version": 1, "title": "미개선 이관", "status": "active", "event_type": "COOLING_ANOMALY", "assets": ["HYD-01", "HYD-02"], "allows": ["ESCALATE"]},
    "SOP-SEN-001@v1": {"doc_id": "SOP-SEN-001", "version": 1, "title": "센서 오류 점검", "status": "active", "event_type": "SENSOR_FAULT", "assets": ["HYD-01", "HYD-02"], "allows": ["SENSOR_CHECK"]},
}
ACTIONS = {
    "REDUCE_LOAD": {"action_id": "REDUCE_LOAD", "name": "승인 부하 감소", "min_value": 0.6, "max_value": 1.0, "default_value": 0.8, "requires_approval": True},
    "FAN_BOOST": {"action_id": "FAN_BOOST", "name": "냉각 팬 증속", "min_value": 1.0, "max_value": 1.5, "default_value": 1.3, "requires_approval": True},
    "ESCALATE": {"action_id": "ESCALATE", "name": "정비 책임자 이관", "min_value": None, "max_value": None, "default_value": None, "requires_approval": False},
    "SENSOR_CHECK": {"action_id": "SENSOR_CHECK", "name": "센서 점검 요청", "min_value": None, "max_value": None, "default_value": None, "requires_approval": False},
}


def _sop_obj(key):
    s = SOPS[key]
    return {"sop_key": key, **{k: s[k] for k in ("doc_id", "version", "title", "status", "event_type")}}


def _fake_handler(request: httpx.Request) -> httpx.Response:
    path = unquote(request.url.path).split("/studio/schemas/HydraulicOps/objects/")[1].split("/")
    if request.method == "POST" and path[1] == "fetch":
        filters = json.loads(request.content or b"{}").get("filters", {})
        if path[0] == "Asset":
            objs = [a for a in ASSETS.values() if all(a.get(k) == v for k, v in filters.items())]
        elif path[0] == "SOP":
            objs = [_sop_obj(k) for k, s in SOPS.items() if all(s.get(k2) == v for k2, v in filters.items())]
        else:
            return httpx.Response(404, json={"detail": "class"})
        return httpx.Response(200, json={"count": len(objs), "objects": objs})
    if request.method == "GET" and path[2] == "related":
        cname, key, rel = path[0], path[1], path[3]
        if (cname, rel) == ("Asset", "HAS_SENSOR"):
            objs = [{"sensor_id": f"{key}.{c}", "code": c, "quantity": q, "unit": u, "hz": h} for c, q, u, h in (("TS1", "temperature", "°C", 1), ("PS1", "pressure", "bar", 100), ("FS1", "flow", "L/min", 10))]
        elif (cname, rel) == ("Asset", "GOVERNED_BY"):
            objs = [_sop_obj(k) for k, s in reversed(list(SOPS.items())) if key in s["assets"]]
        elif (cname, rel) == ("SOP", "ALLOWS"):
            objs = [ACTIONS[a] for a in SOPS[key]["allows"]]
        else:
            return httpx.Response(404, json={"detail": "rel"})
        return httpx.Response(200, json={"count": len(objs), "objects": objs})
    return httpx.Response(405, json={"detail": "쓰기 호출 금지"})


@pytest.fixture()
def fake():
    return P.PlatformContext(base_url="http://fake-platform", client=httpx.Client(transport=httpx.MockTransport(_fake_handler)))


def _local_like(asset_id):
    """로컬 graph.asset_context 가 돌려주는 모양 (가짜 데이터 기준)."""
    sops = sorted([s for s in SOPS.values() if asset_id in s["assets"]], key=lambda s: (s["event_type"] != "COOLING_ANOMALY", s["doc_id"]))
    allowed = {}
    for s in sops:
        for a in s["allows"]:
            allowed.setdefault(a, ACTIONS[a])
    return {
        "asset_id": asset_id, "found": True, "asset": {**ASSETS[asset_id], "educational": True},
        "sensors": sorted([{"sensor_id": f"{asset_id}.{c}", "code": c, "quantity": q, "unit": u, "hz": h} for c, q, u, h in (("TS1", "temperature", "°C", 1), ("PS1", "pressure", "bar", 100), ("FS1", "flow", "L/min", 10))], key=lambda x: x["code"]),
        "applicable_sops": [{"doc_id": s["doc_id"], "version": s["version"], "title": s["title"], "effective_date": "2026-09-01", "approver_role": "설비 담당자"} for s in sops],
        "allowed_actions": list(allowed.values()),
    }


def test_missing_asset_is_not_found(fake):
    assert fake.asset_context("HYD-99") == {"asset_id": "HYD-99", "found": False}


def test_sops_come_from_relationship_not_class_scan(fake):
    ctx = fake.asset_context("HYD-02")
    docs = [s["doc_id"] for s in ctx["applicable_sops"]]
    assert "SOP-COOL-001" not in docs and "SOP-LOAD-001" not in docs, "다른 설비(HYD-01)의 SOP 가 섞였다"
    assert docs == ["SOP-COOL-002", "SOP-ESC-001", "SOP-SEN-001"], "순서는 COOLING_ANOMALY 먼저, doc_id 순"
    assert [a["action_id"] for a in ctx["allowed_actions"]] == ["FAN_BOOST", "ESCALATE", "SENSOR_CHECK"]


def test_same_shape_as_local(fake):
    ctx = fake.asset_context("HYD-01")
    local = _local_like("HYD-01")
    assert set(local) <= set(ctx)
    assert [s["code"] for s in ctx["sensors"]] == ["FS1", "PS1", "TS1"]
    assert [a["action_id"] for a in ctx["allowed_actions"]].count("REDUCE_LOAD") == 1, "REDUCE_LOAD 가 중복됐다"
    assert all(set(s) == {"doc_id", "version", "title", "effective_date", "approver_role"} for s in ctx["applicable_sops"])


def test_compare_separates_mismatch_from_field_gaps(fake):
    local = _local_like("HYD-01")
    cmp_ = P.compare_contexts(local, fake.asset_context("HYD-01"))
    assert cmp_["match"] is True and cmp_["sensors_equal"] and cmp_["sops_equal"] and cmp_["actions_equal"]
    assert cmp_["field_gaps"] == ["applicable_sops.approver_role", "applicable_sops.effective_date", "asset.educational"]
    assert cmp_["only_local"] == {} and cmp_["only_platform"] == {}

    wrong = json.loads(json.dumps(fake.asset_context("HYD-01")))
    wrong["applicable_sops"].append({"doc_id": "SOP-COOL-002", "version": 1, "title": "x", "effective_date": None, "approver_role": None})
    bad = P.compare_contexts(local, wrong)
    assert bad["match"] is False and bad["sops_equal"] is False
    assert bad["only_platform"] == {"sops": [("SOP-COOL-002", 1)]}


def test_compare_not_found():
    r = P.compare_contexts({"asset_id": "HYD-99", "found": False}, {"asset_id": "HYD-99", "found": False})
    assert r["match"] is True and r["found"] == [False, False]


def test_context_provider_swap_restores():
    from hydops.b7_agent import tools as T

    original = T.get_asset_context_impl
    with P.use_context_provider(lambda a: {"asset_id": a, "found": False, "source": "stub"}):
        assert T.get_asset_context_impl("HYD-01")["source"] == "stub"
    assert T.get_asset_context_impl is original


# ---- 2부: 실행 중인 교육용 플랫폼 (읽기 전용) ------------------------------------------------
def _platform_ready() -> bool:
    try:
        schemas = httpx.get(f"{PLATFORM}/studio/schemas", timeout=3).json()
    except Exception:  # noqa: BLE001
        return False
    return any(s["schema_name"] == "HydraulicOps" and s.get("published_version") for s in schemas)


live = pytest.mark.skipif(not _platform_ready(), reason="교육용 플랫폼(:8910)이 없거나 HydraulicOps 가 발행되지 않았다")


@live
@pytest.mark.parametrize("asset_id", ["HYD-01", "HYD-02"])
def test_live_platform_matches_local(asset_id):
    pc = P.PlatformContext(base_url=PLATFORM)
    plat = pc.asset_context(asset_id)
    local = P.local_context(asset_id)
    r = P.compare_contexts(local, plat)
    assert r["match"] is True, r
    assert "asset.educational" in r["field_gaps"]
    assert all(c.startswith("GET ") or c.endswith("/fetch") for c in pc.calls), pc.calls
    other = "SOP-COOL-002" if asset_id == "HYD-01" else "SOP-COOL-001"
    assert other not in [s["doc_id"] for s in plat["applicable_sops"]]


@live
def test_live_missing_and_new_asset():
    pc = P.PlatformContext(base_url=PLATFORM)
    assert pc.asset_context("HYD-99") == {"asset_id": "HYD-99", "found": False}
    h3 = pc.asset_context("HYD-03")
    assert h3["found"] is True and h3["applicable_sops"] == [] and h3["allowed_actions"] == []


@live
def test_live_recent_state_behavior():
    rows = P.PlatformContext(base_url=PLATFORM).recent_state("HYD-01")
    assert {r["sensor_id"] for r in rows} == {"FS1", "PS1", "TS1"}
    assert all({"unit", "samples", "avg_valid", "bad_quality"} <= set(r) for r in rows)
