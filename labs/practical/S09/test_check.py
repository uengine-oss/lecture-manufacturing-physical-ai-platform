"""S09 확인 테스트 — 게시 앱 설정·바인딩과 새 센서 별칭 매핑.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S09 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S09 -q

앱을 게시하지 않고, 별칭을 PUT 하지 않고, 관측을 적재하지 않는다. 서버(:8800, :8910)에는 GET 만 보낸다(없으면 건너뜀).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import httpx
import pytest

from hydops.b2_quality.checks import SensorQualityChecker

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SYSTEM = HERE.parents[2] / "system"

spec = importlib.util.spec_from_file_location(f"s09_alias_{BASE.name}", BASE / "alias_mapping.py")
alias = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alias)


def read_js_object(path: Path, var: str) -> dict:
    """`window.X = {...};` 형태의 파일에서 JSON 객체를 읽는다 (// 주석 줄은 무시)."""
    text = "\n".join(l for l in path.read_text().splitlines() if not l.strip().startswith("//"))
    m = re.search(rf"window\.{var}\s*=\s*(\{{.*\}})\s*;", text, re.S)
    assert m, f"{path.name} 에 window.{var} = {{...}}; 가 없다"
    return json.loads(m[1])


CFG = read_js_object(BASE / "config.js", "APP_CONFIG")
BIND = read_js_object(BASE / "binding.js", "APP_BINDING")
TEMPLATE = (SYSTEM / "labplatform" / "app_templates" / "ops-console" / "index.html").read_text()
PROCESS = json.loads((SYSTEM / "labplatform" / "templates" / "process_cooling_response.json").read_text())
PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}")
RUNTIME_KEYS = {"asset_id", "event_id", "workitem_id", "draft", "form"}

# 실제 플랫폼 폐루프 기록의 '정상 회복' 사건 (out/e2e_platform_report.json)
CASE = json.loads((SYSTEM / "out" / "e2e_platform_report.json").read_text())["cases"][0]
EVENT = {**{k: CASE["form_prefilled"][k] for k in ("event_id", "asset_id", "run_id")}, "event_type": "COOLING_ANOMALY", "process_ref": {"instance_id": CASE["instance_id"]}}


def fill(tpl, ctx: dict):
    def look(path):
        cur = ctx
        for p in path.split("."):
            cur = cur[p]
        return cur

    if isinstance(tpl, str):
        m = PH.fullmatch(tpl)
        if m:
            return look(m[1])
        return PH.sub(lambda x: str(look(x[1])), tpl)
    if isinstance(tpl, dict):
        return {k: fill(v, ctx) for k, v in tpl.items()}
    return tpl


CTX = {**CFG, "asset_id": "HYD-01", "event_id": EVENT["event_id"], "event": EVENT, "workitem_id": f"{CASE['instance_id']}:approve", "draft": {"decision": "APPROVED"}}


# ---------------------------------------------------------------- 1. 앱 설정
def test_config_has_required_bindings_from_apps_py():
    required = json.loads(re.search(r"required = (\[.*?\])", (SYSTEM / "labplatform" / "apps.py").read_text())[1].replace("'", '"'))
    missing = [k for k in required if k not in CFG]
    assert not missing, f"apps.py 필수 바인딩 누락: {missing}"


def test_config_points_to_right_servers():
    assert CFG["hydops_api"].rstrip("/").endswith(":8800"), "분석·시뮬레이터 서버(hydops)는 :8800"
    assert CFG["platform_api"].rstrip("/").endswith(":8910"), "교육용 플랫폼은 :8910"
    assert CFG["schema_name"] == "HydraulicOps"
    assert CFG["process_def_id"] == PROCESS["def_id"]


# ---------------------------------------------------------------- 2. 화면 바인딩
def test_placeholders_are_config_keys_or_screen_values():
    for name, b in BIND.items():
        for ph in PH.findall(json.dumps(b)):
            root = ph.split(".")[0]
            assert root in CFG or root in RUNTIME_KEYS or root == "event", f"{name}: 알 수 없는 자리표시자 {{{ph}}}"


def test_studio_bindings():
    assert fill(BIND["assets"]["url"], CTX) == "http://localhost:8910/studio/schemas/HydraulicOps/objects/Asset/fetch" and BIND["assets"]["method"] == "POST"
    assert fill(BIND["events"]["url"], CTX) == "http://localhost:8910/studio/schemas/HydraulicOps/objects/Asset/HYD-01/related/HAS_EVENT"
    assert "/related/HAS_EVENT" in TEMPLATE and "/objects/Asset/fetch" in TEMPLATE  # 제공 화면과 같은 경로


def test_event_detail_reads_hydops_record():
    assert BIND["event_detail"]["url"].startswith("{hydops_api}"), "사건 기록(승인·조치·재측정)은 hydops 서버가 가진다"
    assert fill(BIND["event_detail"]["url"], CTX) == f"http://localhost:8800/api/events/{EVENT['event_id']}"
    assert "${cfg.hydops_api}/api/events/" in TEMPLATE


def test_shipped_template_takes_approval_value_from_form():
    """제공 화면이 승인값을 폼에서 가져오는지 (고정 0.8 이 아닌지) 정적으로 확인한다."""
    assert "approved_value: 0.8" not in TEMPLATE
    assert "draftFor" in TEMPLATE and "f.approved_value" in TEMPLATE


def test_start_payload_matches_intake_form():
    body = fill(BIND["start_work"]["body"], CTX)
    required = [f["name"] for f in PROCESS["activities"][0]["fields"] if f.get("required")]
    assert sorted(body["values"]) == sorted(required), f"접수 폼 필수 입력 {required} 과 같아야 한다"
    assert body["values"]["event_id"] == EVENT["event_id"] and body["values"]["run_id"] == EVENT["run_id"]
    assert fill(BIND["start_work"]["url"], CTX) == "http://localhost:8910/process/definitions/cooling_response/start"


def test_same_event_across_screen_process_action():
    """화면 선택 event_id → 사건 상세 URL · 업무 시작 입력 · 인스턴스 조회가 같은 사건을 가리킨다."""
    detail = fill(BIND["event_detail"]["url"], CTX)
    start = fill(BIND["start_work"]["body"], CTX)["values"]["event_id"]
    inst = fill(BIND["instance"]["url"], CTX)
    assert detail.endswith(EVENT["event_id"]) and start == EVENT["event_id"] and inst.endswith(CASE["instance_id"])


@pytest.mark.parametrize("action_id,proposed", [("REDUCE_LOAD", 0.8), ("FAN_BOOST", 1.3)])
def test_approval_draft_takes_value_from_work_form(action_id, proposed):
    """승인 초안의 승인값은 워크리스트 폼(approved_value 기본값 = 제안값)에서 가져온다.
    이전 제공 화면은 draft.approved_value 를 0.8 로 고정해 HYD-02 FAN_BOOST(1.0~1.5) 제안에도 0.8 을 보냈다(범위 이탈 → 이관).
    현재 index.html 은 태스크마다(draftFor = workitem_id) 폼의 approved_value ?? proposed_value 로 채운다 — 같은 규칙을 검사한다."""
    form = {"action_id": action_id, "proposed_value": proposed, "approved_value": proposed}
    draft = fill(BIND["approval_draft"], CTX | {"form": form})
    assert draft["approved_value"] == proposed
    assert draft["decision"] in ("APPROVED", "REJECTED")


def test_get_bindings_answer_on_running_servers():
    try:
        httpx.get(CFG["platform_api"] + "/health", timeout=3)
        httpx.get("http://localhost:8800/api/state", timeout=3)
    except httpx.HTTPError:
        pytest.skip("서버가 떠 있지 않다")
    r = httpx.get(fill(BIND["events"]["url"], CTX), timeout=10)
    if r.status_code == 409:
        pytest.skip("스키마가 아직 발행되지 않았다")
    assert r.status_code == 200 and r.json()["relationship"] == "HAS_EVENT"
    objs = r.json()["objects"]
    if not objs:
        pytest.skip("HYD-01 사건이 아직 없다")
    d = httpx.get(fill(BIND["event_detail"]["url"], CTX | {"event_id": objs[0]["event_id"]}), timeout=10)
    assert d.status_code == 200 and d.json()["event"]["event_id"] == objs[0]["event_id"]


# ---------------------------------------------------------------- 3. 새 센서 별칭 매핑
SENSORS = [
    {"sensor_id": "HYD-01.FS1", "code": "FS1", "unit": "L/min", "aliases": ["cooler_flow"]},
    {"sensor_id": "HYD-01.PS1", "code": "PS1", "unit": "bar", "aliases": ["main_pressure"]},
    {"sensor_id": "HYD-01.TS1", "code": "TS1", "unit": "°C", "aliases": ["tank_temp", "TT-101"]},
]
GATEWAY = [
    {"sensor": "TT-101", "ts": "2027-01-29T15:00:01+00:00", "value": 45.1, "unit": "degC"},
    {"sensor": "main_pressure", "ts": "2027-01-29T15:00:01+00:00", "value": 150.2, "unit": "bar"},
    {"sensor": "cooler_flow", "ts": "2027-01-29T15:00:01+00:00", "value": 9.0, "unit": "lpm"},
    {"sensor": "TS1", "ts": "2027-01-29T15:00:02+00:00", "value": 45.2},
]


def test_aliases_map_to_standard_codes_and_units():
    rows = alias.map_gateway_rows("HYD-01", GATEWAY, SENSORS)
    assert [(r["sensor_id"], r["unit"]) for r in rows] == [("TS1", "°C"), ("PS1", "bar"), ("FS1", "L/min"), ("TS1", "°C")]
    flags = [r["quality_flag"] for r in SensorQualityChecker().check_many(rows)]
    assert flags == ["OK"] * 4


@pytest.mark.parametrize("name", ["tt-101", "TS10", "PS10", "ts1_backup", "tank_temp_2", "TEMP"])
def test_near_miss_names_are_not_guessed(name):
    assert alias.resolve_sensor(SENSORS, name) is None


def test_unknown_alias_rejects_whole_batch():
    with pytest.raises(alias.UnknownAliasError) as e:
        alias.map_gateway_rows("HYD-01", GATEWAY + [{"sensor": "oil_temp_B", "ts": "2027-01-29T15:00:03+00:00", "value": 47.0}], SENSORS)
    assert e.value.unknown == ["oil_temp_B"]


def test_alias_conflict_detected():
    bad = [dict(s) for s in SENSORS]
    bad[2] = {**bad[2], "aliases": ["tank_temp", "main_pressure"]}
    assert alias.alias_conflicts(SENSORS) == []
    assert alias.alias_conflicts(bad) == ["main_pressure"]
