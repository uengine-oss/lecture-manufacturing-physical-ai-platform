"""실전반 S03 확인 테스트.

cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S03 -q
정답본 확인: LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S03 -q
Neo4j 는 읽기만 한다 (강사가 seed_graph 로 적재해 둔 그래프).
PostgreSQL 에는 LAB-S03- 로 시작하는 run 만 쓰고, 테스트가 끝나면 그 행만 지운다.
"""
import importlib.util
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
TARGET = HERE / ("solution" if os.environ.get("LAB_SOLUTION") == "1" else "") / "context_queries.py"
T0 = datetime(2026, 9, 3, tzinfo=timezone.utc)  # 재생 시각 (수업 서버의 현재 시각보다 이르게)


def _load():
    spec = importlib.util.spec_from_file_location("lab_s03_context", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


def test_queries_are_parameterized():
    for name in ("Q_ASSET_SENSORS", "Q_APPLICABLE_SOP", "Q_ASSET_CONTEXT"):
        text = getattr(m, name)
        assert "$asset_id" in text, name
        assert not re.search(r"HYD-0\d", text), f"{name} 에 설비 ID 를 박아 넣지 않는다"
    assert "$event_type" in m.Q_APPLICABLE_SOP


def test_asset_sensors_only_that_asset():
    rows = m.asset_sensors("HYD-02")
    assert [r["sensor_id"] for r in rows] == ["HYD-02.FS1", "HYD-02.PS1", "HYD-02.TS1"]
    assert {r["code"]: r["unit"] for r in rows} == {"FS1": "L/min", "PS1": "bar", "TS1": "°C"}


def _doc_versions(rows):
    return {(r["doc_id"], r["version"]) for r in rows}


def test_hyd02_never_gets_hyd01_sop():
    h2 = m.applicable_sops("HYD-02", "COOLING_ANOMALY")
    docs = {d for d, _ in _doc_versions(h2)}
    assert "SOP-COOL-002" in docs
    assert "SOP-COOL-001" not in docs and "SOP-LOAD-001" not in docs
    actions = {a["action_id"] for r in h2 for a in r["allowed_actions"]}
    assert "FAN_BOOST" in actions and "REDUCE_LOAD" not in actions
    fan = next(a for r in h2 for a in r["allowed_actions"] if a["action_id"] == "FAN_BOOST")
    assert (fan["min_value"], fan["max_value"], fan["default_value"]) == (1.0, 1.5, 1.3)


def test_hyd01_only_active_versions():
    h1 = m.applicable_sops("HYD-01", "COOLING_ANOMALY")
    dv = _doc_versions(h1)
    assert ("SOP-COOL-001", 2) in dv and ("SOP-COOL-001", 1) not in dv
    assert "SOP-COOL-002" not in {d for d, _ in dv}
    sen = m.applicable_sops("HYD-01", "SENSOR_FAULT")
    assert _doc_versions(sen) == {("SOP-SEN-001", 1)}


def test_asset_context_distinguishes_no_sop_from_no_asset():
    h3 = m.asset_context("HYD-03")
    assert h3["found"] is True, "HYD-03 은 존재하는 설비다 (SOP 가 없을 뿐)"
    assert h3["active_sops"] == [] and h3["allowed_actions"] == []
    assert m.asset_context("HYD-99")["found"] is False
    h1 = m.asset_context("HYD-01")
    assert "SOP-COOL-001@v1" not in h1["active_sops"] and "SOP-COOL-001@v2" in h1["active_sops"]
    assert h1["component"] == "HYD-01.COOLER"


@pytest.fixture(scope="module")
def lab_run_hyd02():
    from hydops.b1_data import uci
    from hydops.b2_quality.checks import SensorQualityChecker
    from hydops.b3_tsdb import store

    run_id = f"LAB-S03-{uuid.uuid4().hex[:8]}"
    ds = uci.load_reduced()
    rows = SensorQualityChecker().check_many(uci.cycle_observations(ds, 100, "HYD-02", T0))
    store.create_run("uci_replay", "lab-s03", note="S03 결합 실습", run_id=run_id)
    store.insert_observations(run_id, rows)
    yield run_id, rows
    with store.connect() as c:
        c.execute("DELETE FROM observation WHERE run_id=%s", (run_id,))
        c.execute("DELETE FROM run WHERE run_id=%s", (run_id,))


def test_join_graph_and_recent_window_by_asset(lab_run_hyd02):
    run_id, rows = lab_run_hyd02
    out = m.join_recent("HYD-02", run_id, 60)
    assert out["asset_id"] == "HYD-02"
    assert {s["doc_id"] for s in out["cooling_sops"]} >= {"SOP-COOL-002"}
    assert "SOP-COOL-001" not in {s["doc_id"] for s in out["cooling_sops"]}
    by = {s["code"]: s for s in out["sensors"]}
    assert set(by) == {"TS1", "PS1", "FS1"}
    for code, s in by.items():
        assert s["samples"] == 60, code
        assert s["unit_match"] is True, code
    last_ts1 = [r for r in rows if r["sensor_id"] == "TS1"][-1]["value"]
    assert by["TS1"]["last_valid"] == pytest.approx(round(last_ts1, 2))
    assert by["TS1"]["sensor_state"] == "VALID"
