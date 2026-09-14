"""통합반 S03 점검 — MERGE 문장의 ID, 세 가지 Cypher 질의, 그래프+시계열 결합.

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S03 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
- 질의는 읽기 전용 세션으로만 실행한다.
- MERGE 는 강사 시드와 같은 값일 때만 반영된다(새 노드·관계가 생기면 되돌린다).
- PostgreSQL 에는 run_id 가 LAB-S03- 로 시작하는 행만 쓰고 끝나면 지운다.
"""
import importlib.util
import os
from pathlib import Path

import pytest

from hydops.b4_ontology import graph

HERE = Path(__file__).resolve().parent
SRC = (HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE) / "graph_lab.py"


def _load():
    spec = importlib.util.spec_from_file_location("s03_graph_lab", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab = _load()


def test_merge_ids_match_seed():
    before = graph.graph_stats()
    results = lab.seed_check()
    for r in results:
        assert r["committed"], f"[빈칸 1] {r['what']}: 시드와 다른 ID → 되돌림 ({r})"
        assert r["merged"] and r["nodes_created"] == 0 and r["relationships_created"] == 0
    assert results[0]["merged"] == ["HYD-01.TS1"]
    assert graph.graph_stats()["nodes"]["Sensor"] == before["nodes"]["Sensor"]


def test_q1_asset_sensors():
    for asset_id in ("HYD-01", "HYD-02", "HYD-03"):
        got = lab.run_read(lab.Q_ASSET_SENSORS, asset_id=asset_id)
        assert got == graph.asset_sensors(asset_id), f"[빈칸 2] {asset_id}"
    assert [r["sensor_id"] for r in lab.run_read(lab.Q_ASSET_SENSORS, asset_id="HYD-02")] == ["HYD-02.FS1", "HYD-02.PS1", "HYD-02.TS1"]


def _sop_set(asset_id, event_type):
    return {(r["doc_id"], r["version"]) for r in lab.run_read(lab.Q_APPLICABLE_SOP, asset_id=asset_id, event_type=event_type)}


def test_q2_applicable_sop_not_mixed():
    for asset_id in ("HYD-01", "HYD-02", "HYD-03"):
        for et in ("COOLING_ANOMALY", "SENSOR_FAULT"):
            ref = {(s["doc_id"], s["version"]) for s in graph.applicable_sops(asset_id, et)}
            assert _sop_set(asset_id, et) == ref, f"[빈칸 3] {asset_id} {et}"
    h1 = _sop_set("HYD-01", "COOLING_ANOMALY")
    assert ("SOP-COOL-001", 2) in h1 and ("SOP-COOL-001", 1) not in h1, "폐기된 1판이 섞이면 안 된다"
    assert all(d != "SOP-COOL-002" for d, _ in h1), "HYD-02 의 SOP 가 섞이면 안 된다"
    assert _sop_set("HYD-03", "COOLING_ANOMALY") == set()
    rows = lab.run_read(lab.Q_APPLICABLE_SOP, asset_id="HYD-02", event_type="COOLING_ANOMALY")
    assert "FAN_BOOST" in {a for r in rows for a in r["allowed_actions"]}


def test_q3_event_evidence():
    event_id = lab.any_event_with_citation()
    if event_id is None:
        pytest.skip("인용이 연결된 사건이 그래프에 없다 — 관제 화면에서 사건을 하나 처리한 뒤 다시 실행")
    got = lab.run_read(lab.Q_EVENT_EVIDENCE, event_id=event_id)
    ref = graph.event_evidence(event_id)
    assert got, "[빈칸 4] 결과가 비었다"
    assert got[0]["asset_id"] == ref["asset_id"]
    ref_cites = {f"{c['doc_id']} v{c['version']} §{c['section']}" for c in ref["citations"] if c.get("doc_id")}
    assert set(got[0]["citations"]) == ref_cites and ref_cites, "[빈칸 4] 인용 절"


def test_graph_joined_with_recent_values():
    run_id = lab.load_lab_cycle()
    try:
        rows = {r["sensor_id"]: r for r in lab.sensors_with_recent_values("HYD-01", run_id)}
    finally:
        lab.cleanup(run_id)
    assert set(rows) == {"HYD-01.TS1", "HYD-01.PS1", "HYD-01.FS1"}
    for r in rows.values():
        assert r["n"] == 60, "[빈칸 5] observation 의 sensor_id 는 센서 코드(TS1)로 저장돼 있다"
        assert r["unit_graph"] == r["unit_db"] and r["origin_cycle_id"] == 100
    assert rows["HYD-01.TS1"]["last_value"] == 53.395
