"""실전반 S02 확인 테스트.

cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S02 -q
정답본 확인: LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S02 -q
DB 에는 LAB-S02- 로 시작하는 run 만 쓰고, 테스트가 끝나면 그 행만 지운다.
"""
import importlib.util
import os
import uuid
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
TARGET = HERE / ("solution" if os.environ.get("LAB_SOLUTION") == "1" else "") / "quality.py"
T0 = datetime(2026, 9, 2, tzinfo=timezone.utc)  # 재생 시각 (수업 서버의 현재 시각보다 이르게)


def _load():
    spec = importlib.util.spec_from_file_location("lab_s02_quality", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


q = _load()


def _series(values, sensor_id="TS1", asset_id="HYD-01"):
    return [
        {"asset_id": asset_id, "sensor_id": sensor_id, "ts": T0 + timedelta(seconds=i), "elapsed_s": i, "origin_cycle_id": None,
         "raw_value": v, "unit": "°C", "agg": None, "is_synthetic": True}
        for i, v in enumerate(values)
    ]


def _flags(rows):
    return [r["quality_flag"] for r in rows]


@pytest.fixture(scope="module")
def injected_1500():
    from hydops.b1_data import uci

    ds = uci.load_reduced()
    rows = uci.inject_sensor_errors(uci.cycle_observations(ds, 1500, "HYD-01", T0))
    return q.LabQualityChecker().check_many(rows)


def test_aggregate_1s_keeps_missing_visible():
    from hydops.config import DATA_DIR

    with open(DATA_DIR / "raw" / "PS1.txt") as f:
        samples = np.array(next(islice(f, 100, 101)).split("\t"), dtype=float)
    ref = samples.reshape(60, 100)
    samples = samples.copy()
    samples[500:600] = np.nan          # 5초: 샘플 전부 결측
    samples[600:670] = np.nan          # 6초: 30개만 유효
    samples[700:720] = np.nan          # 7초: 80개 유효
    secs = q.aggregate_1s(samples, 100)
    assert len(secs) == 60
    assert secs[5]["mean"] is None and secs[5]["n"] == 0
    assert secs[6]["mean"] is None and secs[6]["n"] == 30
    assert secs[7]["n"] == 80 and secs[7]["mean"] == pytest.approx(ref[7][20:].mean())
    assert secs[8]["n"] == 100 and secs[8]["mean"] == pytest.approx(ref[8].mean())


def test_long_gap_not_hidden_uci_1500(injected_1500):
    from hydops.b2_quality.checks import window_quality

    ts1 = [r for r in injected_1500 if r["sensor_id"] == "TS1"]
    wq = window_quality(ts1)
    assert wq["flags"] == {"OK": 49, "SPIKE": 1, "MISSING": 4, "GAP": 3, "STUCK": 3}
    assert wq["longest_gap_s"] == 7
    assert all(r["value"] is None for r in ts1 if r["quality_flag"] != "OK"), "품질 불량 관측의 정제 값은 비워야 한다"


def test_stuck_starts_at_eighth_same_value():
    rows = q.LabQualityChecker().check_many(_series([45.1, 45.3, 45.2] + [45.0] * 10 + [45.4]))
    assert _flags(rows).count("STUCK") == 3
    assert _flags(rows)[3 + 7] == "STUCK" and _flags(rows)[3 + 6] == "OK"


def test_single_spike_rejected_level_shift_accepted():
    base = [45.0 + 0.1 * (i % 3) for i in range(10)]
    one = q.LabQualityChecker().check_many(_series(base + [70.0] + base))
    assert _flags(one).count("SPIKE") == 1 and _flags(one)[11] == "OK"

    shift = [60.0 + 0.1 * (i % 3) for i in range(15)]
    rows = q.LabQualityChecker().check_many(_series(base + shift))
    f = _flags(rows)
    assert f[10:12] == ["SPIKE", "SPIKE"], "처음 두 번은 급등으로 막는다"
    assert f[12:] == ["OK"] * 13, "세 번째부터 수준 변화로 받아들인다"


def _severe_degradation(extra_fault=None):
    from hydops.b1_data.simulator import HydraulicSimulator

    sim = HydraulicSimulator("HYD-01", seed=7, start=T0)
    rows = sim.run(20)
    sim.inject_cooling_degradation(0.25)
    rows += sim.run(60)
    if extra_fault:
        sim.inject_sensor_fault(extra_fault, 15)
        rows += sim.run(20)
    return [r for r in rows if r["sensor_id"] == "TS1"]


def test_fast_rise_is_not_spike():
    rows = q.LabQualityChecker().check_many(_severe_degradation())
    assert _flags(rows).count("SPIKE") == 0, "냉각 심각 저하(0.25)의 빠른 상승은 급등이 아니다"
    st = q.window_state(rows[-60:])
    assert st["state"] == "EQUIPMENT_ANOMALY"


def test_stuck_at_high_temp_is_sensor_fault_not_equipment():
    rows = q.LabQualityChecker().check_many(_severe_degradation("stuck"))
    st = q.window_state(rows[-60:])
    assert st["state"] == "SENSOR_FAULT"


def test_window_state_normal_and_injected(injected_1500):
    ts1 = [r for r in injected_1500 if r["sensor_id"] == "TS1"]
    assert q.window_state(ts1)["state"] == "SENSOR_FAULT"
    from hydops.b1_data.simulator import HydraulicSimulator

    normal = q.LabQualityChecker().check_many([r for r in HydraulicSimulator("HYD-01", seed=7, start=T0).run(60) if r["sensor_id"] == "TS1"])
    assert q.window_state(normal)["state"] == "NORMAL"


@pytest.fixture()
def lab_run():
    run_id = f"LAB-S02-{uuid.uuid4().hex[:8]}"
    yield run_id
    q.delete_lab_run(run_id)


def test_store_raw_clean_flag(lab_run, injected_1500):
    from hydops.b3_tsdb import store

    assert q.store_checked(lab_run, injected_1500) == 180
    with store.connect() as c:
        agg = c.execute(
            """SELECT count(*) FILTER (WHERE raw_value IS NULL) AS raw_null,
                      count(*) FILTER (WHERE value IS NULL) AS value_null,
                      count(*) FILTER (WHERE quality_flag='GAP') AS gap,
                      count(*) FILTER (WHERE quality_flag='SPIKE' AND raw_value IS NOT NULL AND value IS NULL) AS spike_kept_raw,
                      count(*) FILTER (WHERE quality_flag='STUCK' AND raw_value IS NOT NULL) AS stuck_kept_raw
               FROM observation WHERE run_id=%s AND sensor_id='TS1'""",
            (lab_run,),
        ).fetchone()
    assert agg["raw_null"] == 7, "결측 7초만 원시 값이 비어 있어야 한다"
    assert agg["value_null"] == 11
    assert agg["gap"] == 3 and agg["spike_kept_raw"] == 1 and agg["stuck_kept_raw"] == 3
