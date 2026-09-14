"""통합반 7회 실습 검사 — 기본은 학생 파일, LAB_SOLUTION=1 이면 solution/ 을 검사한다.

플랫폼 서버(:8910)·관제 API(:8800)는 GET 만 호출한다. 서버가 꺼져 있으면 해당 검사는 건너뛴다.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SYSTEM = HERE.parents[2] / "system"
TEMPLATE = json.loads((SYSTEM / "labplatform" / "templates" / "ontology_hydraulic.json").read_text())
PLATFORM, HYDOPS = "http://localhost:8910", "http://localhost:8800"


def load_module():
    spec = importlib.util.spec_from_file_location("s07_studio_lookup", SRC / "studio_lookup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def binding() -> dict:
    return json.loads((SRC / "my_binding.json").read_text())


def up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


needs_platform = pytest.mark.skipif(not up(f"{PLATFORM}/health"), reason="교육용 플랫폼(:8910)이 꺼져 있다")
needs_hydops = pytest.mark.skipif(not up(f"{HYDOPS}/api/state"), reason="관제 API(:8800)가 꺼져 있다")


def tpl_class(name: str) -> dict:
    return next(c for c in TEMPLATE["classes"] if c["name"] == name)


# ---- 1. 빈칸 ---------------------------------------------------------------------
def test_no_blanks_left():
    for f in ("my_binding.json", "studio_lookup.py"):
        text = (SRC / f).read_text()
        body = text.replace("____ = None", "").replace("빈칸(____)", "")  # 빈칸 표시 정의·설명은 제외
        assert "____" not in body, f"{f} 에 빈칸(____)이 남아 있다"


# ---- 2. 제공 매핑과 같은가 (정적) ----------------------------------------------------
def test_binding_matches_provided_template():
    b = binding()
    assert b["schema_name"] == TEMPLATE["schema_name"]
    for c in b["classes"]:
        t = tpl_class(c["name"])
        key = next(p["name"] for p in t["properties"] if p.get("key"))
        assert c["key"] == key, f"{c['name']} 키 속성이 틀렸다"
        tb, sb = t["binding"], c["binding"]
        assert sb["kind"] == tb["kind"], f"{c['name']} 바인딩 종류"
        if tb["kind"] == "graph":
            assert sb["label"] == tb["label"], f"{c['name']} 그래프 라벨"
        else:
            assert (sb["datasource"], sb["table"]) == (tb["datasource"], tb["table"]), f"{c['name']} 데이터소스·테이블"
            pairs = {(m["property"], m["column"]) for m in tb["column_map"]}
            for m in sb["column_map"]:
                assert (m["property"], m["column"]) in pairs, f"{c['name']} 속성 {m['property']} → 컬럼 {m['column']} 매핑이 제공 템플릿과 다르다"
    for r in b["relationships"]:
        t = next(x for x in TEMPLATE["relationships"] if x["name"] == r["name"])
        assert (r["from"], r["to"]) == (t["from"], t["to"])
        assert r["via"] == t["via"], f"관계 {r['name']} 조인 속성이 틀렸다"


# ---- 3. Data Fabric 메타데이터로 검증 (GET) -------------------------------------------
@needs_platform
def test_columns_exist_in_fabric_metadata():
    b = binding()
    for c in b["classes"]:
        sb = c["binding"]
        if sb["kind"] != "virtual":
            continue
        r = httpx.get(f"{PLATFORM}/fabric/datasources/{sb['datasource']}", timeout=10)
        assert r.status_code == 200, f"데이터소스 {sb['datasource']} 가 등록돼 있지 않다"
        tables = (r.json().get("metadata") or {}).get("tables", {})
        assert sb["table"] in tables, f"테이블 {sb['table']} 이 메타데이터에 없다"
        cols = {x["name"] for x in tables[sb["table"]]}
        missing = [m["column"] for m in sb["column_map"] if m["column"] not in cols] + ([sb["order_by"]] if sb.get("order_by") and sb["order_by"] not in cols else [])
        assert not missing, f"{c['name']}: 없는 컬럼 {missing}"


# ---- 4. 조회 결과 구분 --------------------------------------------------------------
def test_classify_three_cases_offline():
    m = load_module()
    assert m.classify({"http_status": 409, "detail": "schema HydraulicOps 이 발행되지 않았다"}) == "NOT_PUBLISHED"
    assert m.classify({"http_status": 200, "count": 0, "objects": []}) == "PUBLISHED_NO_DATA"
    assert m.classify({"http_status": 200, "count": 3, "objects": [{}, {}, {}]}) == "HAS_DATA"


@needs_platform
def test_related_url_and_live_sensor_lookup():
    m = load_module()
    assert m.related_url("Asset", "HYD-01", "HAS_SENSOR") == f"{PLATFORM}/studio/schemas/HydraulicOps/objects/Asset/HYD-01/related/HAS_SENSOR"
    res = m.get_related("Asset", "HYD-01", "HAS_SENSOR")
    state = m.classify(res)
    if state == "NOT_PUBLISHED":
        pytest.skip("HydraulicOps 가 아직 발행 전이다 (활동 3 전에는 정상)")
    assert state == "HAS_DATA" and res["count"] == 3


@needs_platform
def test_published_but_no_data_is_reported_as_such():
    m = load_module()
    sc = next((s for s in httpx.get(f"{PLATFORM}/studio/schemas", timeout=10).json() if s["schema_name"] == "HydraulicOps"), None)
    if not sc or not sc.get("published_version"):
        pytest.skip("HydraulicOps 가 아직 발행 전이다")
    # (1) 그래프 관계: HYD-03 은 적용 SOP 가 없는 신규 설비 — note 없이 count 0
    g = m.get_related("Asset", "HYD-03", "GOVERNED_BY")
    assert g["http_status"] == 200 and g["count"] == 0
    assert m.classify(g) == "PUBLISHED_NO_DATA"
    # (2) 가상 연결(조인): 사건이 0개인 설비가 있으면 note 로 '발행 ≠ 데이터 존재' 를 알려준다
    zero = [r for r in (m.get_related("Asset", a, "HAS_EVENT") for a in ("HYD-01", "HYD-02", "HYD-03")) if r.get("count") == 0]
    for r in zero:
        assert m.classify(r) == "PUBLISHED_NO_DATA"
        assert "발행 ≠ 데이터 존재" in (r.get("note") or "")


@needs_platform
@needs_hydops
def test_local_and_platform_show_same_sensors():
    m = load_module()
    res = m.get_related("Asset", "HYD-01", "HAS_SENSOR")
    if m.classify(res) == "NOT_PUBLISHED":
        pytest.skip("HydraulicOps 가 아직 발행 전이다")
    assert m.same_sensors(m.local_asset("HYD-01"), res)
