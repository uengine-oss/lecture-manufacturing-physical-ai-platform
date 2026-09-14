"""통합반 9회 실습 검사 — 기본은 학생 파일, LAB_SOLUTION=1 이면 solution/ 을 검사한다.

앱 설정(config.js)과 데이터 연결(app_bindings.js)을 제공 화면 index.html 과 정적으로 대조하고,
게시된 앱과 조회 주소는 GET(그리고 읽기 전용 객체 조회 fetch)으로만 확인한다. 업무 시작(start)은 호출하지 않는다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SYSTEM = HERE.parents[2] / "system"
INDEX_HTML = (SYSTEM / "labplatform" / "app_templates" / "ops-console" / "index.html").read_text()
APPS_PY = (SYSTEM / "labplatform" / "apps.py").read_text()
PLATFORM, HYDOPS = "http://localhost:8910", "http://localhost:8800"


def up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


needs_servers = pytest.mark.skipif(not (up(f"{PLATFORM}/health") and up(f"{HYDOPS}/api/state")), reason="교육용 플랫폼(:8910) 또는 관제 API(:8800)가 꺼져 있다")


def parse_config(text: str) -> dict:
    m = re.search(r"window\.APP_CONFIG\s*=\s*(\{.*?\});", text, re.S)
    assert m, "window.APP_CONFIG = {...}; 형식이 아니다"
    return json.loads(m[1])


def config() -> dict:
    return parse_config((SRC / "config.js").read_text())


def bindings() -> dict:
    text = (SRC / "app_bindings.js").read_text()
    rows = re.findall(r"(\w+):\s*\{\s*method:\s*'([^']*)',\s*url:\s*'([^']*)'\s*\}", text)
    return {k: {"method": m, "url": u} for k, m, u in rows}


def fill(url: str, **values) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda x: str(values[x[1]]), url)


def same_event_module():
    spec = importlib.util.spec_from_file_location("s09_same_event", SRC / "same_event.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- 1. 빈칸 ---------------------------------------------------------------------
def test_no_blanks_left():
    for f in ("config.js", "app_bindings.js", "same_event.py"):
        body = (SRC / f).read_text().replace("____ = None", "")
        assert "____" not in body, f"{f} 에 빈칸(____)이 남아 있다"


# ---- 2. 앱 설정 (정적) ---------------------------------------------------------------
def test_config_has_required_bindings():
    required = re.search(r"required = (\[.*?\])", APPS_PY)[1]
    cfg = config()
    for k in json.loads(required.replace("'", '"')):
        assert cfg.get(k) and cfg[k] != "____", f"게시 검증이 요구하는 바인딩 {k} 가 비었다"
    assert cfg["hydops_api"].endswith(":8800") and cfg["platform_api"].endswith(":8910")
    assert cfg["schema_name"] == "HydraulicOps" and cfg["process_def_id"] == "cooling_response"


# ---- 3. 데이터 연결이 제공 화면과 같은가 (정적) ------------------------------------------
TO_TEMPLATE = [
    ("${platform_api}/studio/schemas/${schema_name}", "${S}"),
    ("${platform_api}", "${cfg.platform_api}"),
    ("${hydops_api}", "${cfg.hydops_api}"),
    ("${process_def_id}", "${cfg.process_def_id}"),
    ("${asset_id}", "${this.assetId}"),
    ("${event_id}", "${this.eventId}"),
    ("${instance_id}", "${ref.instance_id}"),
]


def test_bindings_match_provided_screen():
    b = bindings()
    assert set(b) >= {"assetList", "assetEvents", "eventDetail", "processInstance", "openWork"}
    for name, x in b.items():
        u = x["url"]
        for a, t in TO_TEMPLATE:
            u = u.replace(a, t)
        assert f"`{u}`" in INDEX_HTML, f"{name}: {x['url']} 가 제공 화면 index.html 의 조회 주소와 다르다"
        is_post = f"post(`{u}`" in INDEX_HTML
        assert x["method"] == ("POST" if is_post else "GET"), f"{name} 메서드"


def test_same_event_checks_offline():
    m = same_event_module()
    detail = {"event": {"event_id": "E1", "process_ref": {"instance_id": "PI-1"}}, "actions": [{"event_id": "E1"}]}
    assert m.instance_id_of(detail) == "PI-1"
    assert m.same_event_checks("E1", detail, {"vars": {"event_id": "E1"}}) == {"화면 event_id": True, "프로세스 입력 event_id": True, "조치 기록 event_id": True}
    no_action = {"event": {"event_id": "E2", "process_ref": None}, "actions": []}
    r = m.same_event_checks("E2", no_action, None)
    assert r["조치 기록 event_id"] is None and r["프로세스 입력 event_id"] is False
    assert m.instance_id_of(no_action) is None
    wrong = m.same_event_checks("E1", detail, {"vars": {"event_id": "E9"}})
    assert wrong["프로세스 입력 event_id"] is False


# ---- 4. 게시된 앱과 실제 조회 (GET) -------------------------------------------------------
@needs_servers
def test_published_app_uses_same_config():
    apps = {a["name"]: a for a in httpx.get(f"{PLATFORM}/apps", timeout=10).json()}
    cfg = config()
    assert cfg["app_name"] in apps, "게시된 앱이 없다 — 활동 3에서 게시한다"
    app = apps[cfg["app_name"]]
    assert app["status"] == "PUBLISHED"
    assert {k: cfg[k] for k in app["config"]} == app["config"]
    served = parse_config(httpx.get(f"{PLATFORM}/apps/{cfg['app_name']}/config.js", timeout=10).text)
    assert served == cfg
    logs = [x["message"] for x in httpx.get(f"{PLATFORM}/apps/{cfg['app_name']}/logs", timeout=10).json()]
    assert any(msg.startswith("게시 완료") for msg in logs)


@needs_servers
def test_bound_urls_return_the_same_event():
    cfg, b, m = config(), bindings(), same_event_module()
    assets = httpx.post(fill(b["assetList"]["url"], **cfg), json={"limit": 10}, timeout=10).json()  # 읽기 전용 객체 조회
    assert "HYD-01" in [a["asset_id"] for a in assets["objects"]]
    events = httpx.get(fill(b["assetEvents"]["url"], **cfg, asset_id="HYD-01"), timeout=10).json()["objects"]
    checked = 0
    for ev in events:
        detail = httpx.get(fill(b["eventDetail"]["url"], **cfg, event_id=ev["event_id"]), timeout=10).json()
        assert detail["event"]["event_id"] == ev["event_id"]
        iid = m.instance_id_of(detail)
        if not iid:
            continue
        inst = httpx.get(fill(b["processInstance"]["url"], **cfg, instance_id=iid), timeout=10).json()
        res = m.same_event_checks(ev["event_id"], detail, inst)
        assert res["화면 event_id"] and res["프로세스 입력 event_id"] and res["조치 기록 event_id"] in (True, None), res
        checked += 1
    if not checked:
        pytest.skip("프로세스 인스턴스와 대응된 HYD-01 사건이 아직 없다")
    start = fill(b["openWork"]["url"], **cfg)
    assert start == f"{PLATFORM}/process/definitions/cooling_response/start"  # 주소만 확인하고 호출하지 않는다
