"""실전반 S01 확인 테스트.

cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S01 -q
정답본 확인: LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S01 -q
DB 에는 LAB-S01- 로 시작하는 run 만 쓰고, 테스트가 끝나면 그 행만 지운다.
"""
import importlib.util
import os
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
TARGET = HERE / ("solution" if os.environ.get("LAB_SOLUTION") == "1" else "") / "mapping.py"


def _load():
    spec = importlib.util.spec_from_file_location("lab_s01_mapping", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()


@pytest.fixture(scope="module")
def reduced():
    from hydops.b1_data import uci

    return uci.load_reduced()


@pytest.fixture(scope="module")
def raw100():
    return {sid: m.read_raw_cycle(sid, 100) for sid in m.SENSOR_SPEC}


def test_reduce_keeps_mean_min_max_n(raw100, reduced):
    secs = m.reduce_to_seconds(raw100["PS1"], 100)
    assert len(secs) == 60
    means = np.array([s["mean"] for s in secs])
    # 강사 제공 축약본(hydraulic_1s.npz)과 같은 1초 평균이어야 한다
    assert np.allclose(means, reduced.sensors["PS1"]["mean"][100], atol=1e-6)
    assert all(s["n"] == 100 for s in secs)
    assert all(s["min"] <= s["mean"] <= s["max"] for s in secs)
    assert any(s["max"] - s["min"] > 1.0 for s in secs), "1초 안의 압력 변동 폭이 남아야 한다"


def test_map_cycle_common_record(raw100):
    from datetime import datetime, timezone

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = m.map_cycle(raw100, 100, "HYD-01", start)
    assert len(rows) == 180
    by = {sid: [r for r in rows if r["sensor_id"] == sid] for sid in ("TS1", "PS1", "FS1")}
    assert {r["unit"] for r in by["TS1"]} == {"°C"}
    assert {r["unit"] for r in by["PS1"]} == {"bar"}
    assert {r["unit"] for r in by["FS1"]} == {"L/min"}
    assert all(r["agg"] is None for r in by["TS1"])
    assert by["PS1"][0]["agg"]["n"] == 100 and by["PS1"][0]["agg"]["source_hz"] == 100
    assert by["FS1"][0]["agg"]["n"] == 10
    assert {r["origin_cycle_id"] for r in rows} == {100}
    assert [r["elapsed_s"] for r in by["TS1"]] == list(range(60))
    assert all(r["is_synthetic"] is False for r in rows)
    assert "cooler_pct" not in rows[0], "정답 라벨은 관측 레코드에 넣지 않는다"


@pytest.fixture(scope="module")
def lab_run():
    run_id = f"LAB-S01-{uuid.uuid4().hex[:8]}"
    yield run_id
    m.delete_lab_run(run_id)


def test_load_and_recent_window_tracks_origin(lab_run):
    from hydops.b3_tsdb import store

    n = m.load_cycles(lab_run, [100, 101, 102], "HYD-01")
    assert n == 540
    with store.connect() as c:
        run = c.execute("SELECT source FROM run WHERE run_id=%s", (lab_run,)).fetchone()
    assert run["source"] == "uci_replay"

    last = m.window_with_origin(lab_run, "HYD-01", 60)
    assert set(last["sensors"]) == {"TS1", "PS1", "FS1"}
    for sid, s in last["sensors"].items():
        assert s["samples"] == 60, sid
        assert s["run_ids"] == [lab_run]
        assert s["origin_cycles"] == [102]
        assert sorted(s["elapsed"]) == list(range(60))
        assert s["is_synthetic"] == [False]
    assert last["sensors"]["PS1"]["unit"] == "bar"

    # 사이클 경계에 걸친 60초: 재생 시작 +90초까지 → 사이클 100 의 31~59초와 101 의 0~30초
    mid = m.window_with_origin(lab_run, "HYD-01", 60, until=m.LAB_REPLAY_START + timedelta(seconds=90))
    ts1 = mid["sensors"]["TS1"]
    assert ts1["origin_cycles"] == [100, 101]
    assert ts1["samples"] == 60
