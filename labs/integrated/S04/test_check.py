"""통합반 S04 점검 — 지속 조건 설정, 사건 유형 구분, 화면 표시 매핑.

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S04 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
DB·서버를 쓰지 않는다 (UCI 축약본 파일 + 메모리 안의 시뮬레이터만 사용).
"""
import importlib.util
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hydops.b1_data.inspection import synth_lots
from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b2_quality.checks import SensorQualityChecker
from hydops.b5_detect import evaluate
from hydops.b5_detect.detector import ThresholdDetector, recent_summary
from hydops.config import ROOT

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE


def _load(name):
    spec = importlib.util.spec_from_file_location(f"s04_{name}_{id(SRC)}", SRC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cfg = _load("detect_config")
et = _load("event_types")


# ---- 시뮬레이터 실행 도우미 (hydops.runtime.PlantRuntime 과 같은 B1→B2→B5 순서, DB 저장만 뺐다) ----
def simulate(inject=None, at=30, total=150, th=None, seed=42, asset_id="HYD-01", **kw):
    sim = HydraulicSimulator(asset_id, seed=seed)
    checker = SensorQualityChecker()
    det = ThresholdDetector(th) if th is not None else None
    ts1_rows, signals = [], []
    for s in range(1, total + 1):
        if s == at + 1:
            if inject == "cooling":
                sim.inject_cooling_degradation(kw.get("eff", 0.4))
            elif inject in ("dropout", "stuck", "spike"):
                sim.inject_sensor_fault(inject, kw.get("seconds", 20))
        for r in checker.check_many(sim.step()):
            if r["sensor_id"] == "TS1":
                ts1_rows.append(r)
            if det is not None:
                signals += [(s, g.event_type) for g in det.feed(r)]
    return ts1_rows, signals


# ---- 1. 시험 구간 고정과 지속 조건 설정 ------------------------------------------------
def test_split_seed_is_fixed():
    assert cfg.SPLIT_SEED == evaluate.SPLIT_SEED, "시험 구간 시드는 evaluate.py 의 SPLIT_SEED 와 같아야 한다"


def test_strict_setting_reproduces_documented_result():
    assert cfg.STRICT == {"k_sigma": 4.0, "min_delta_c": 3.0, "sustain_s": 10, "smooth_s": 5}
    r = evaluate.evaluate(**cfg.STRICT)
    assert (r["baseline_cycles"], r["test_cycles"]) == (244, 180)
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (120, 1, 0, 59)
    assert r["mean_delay_s"] == 9.0


def test_loose_setting_raises_false_alarms():
    assert cfg.LOOSE == {"k_sigma": 2.0, "min_delta_c": 1.0, "sustain_s": 1, "smooth_s": 1}
    strict, loose = evaluate.evaluate(**cfg.STRICT), evaluate.evaluate(**cfg.LOOSE)
    assert loose["fp"] == 4 and strict["fp"] == 1
    assert loose["mean_delay_s"] == 0.0  # 빨리 알리는 대신 오탐이 늘었다


def test_stream_threshold_values():
    assert cfg.STREAM.alarm_temp_c == 60.0 and cfg.STREAM.alarm_sustain_s == 10


def test_stream_single_spike_is_not_an_event():
    rows, signals = simulate("spike", seconds=20, th=cfg.STREAM)
    assert signals == []
    assert sum(r["quality_flag"] == "SPIKE" for r in rows) == 2  # 급등은 품질 플래그로만 남는다


def test_stream_dropout_is_sensor_fault_and_cooling_is_equipment():
    _, s_drop = simulate("dropout", seconds=20, th=cfg.STREAM)
    assert s_drop == [(35, "SENSOR_FAULT")]  # 결측 5초째(GAP)에 센서 오류 사건 하나
    _, s_cool = simulate("cooling", eff=0.4, th=cfg.STREAM)
    assert s_cool == [(52, "COOLING_ANOMALY")]  # 냉각 0.4 주입(t=31) 후 유효 60°C 초과 10초째


# ---- 2. 사건 유형 구분 ----------------------------------------------------------------
@pytest.mark.parametrize(
    "inject,kw,end,expected",
    [
        (None, {}, 90, "NORMAL"),
        ("spike", {"seconds": 20}, 90, "NORMAL"),
        ("dropout", {"seconds": 20}, 60, "SENSOR_FAULT"),
        ("stuck", {"seconds": 15}, 50, "SENSOR_FAULT"),  # 고착이 최근 15초 안에 있을 때
        ("cooling", {"eff": 0.4}, 90, "COOLING_ANOMALY"),
    ],
)
def test_classify_sensor_window_matches_system(inject, kw, end, expected):
    rows, _ = simulate(inject, total=end, **kw)
    ts1 = recent_summary(rows[-60:])["TS1"]
    got = et.classify_sensor_window(ts1)
    assert got == expected
    # 시스템의 요약이 내린 센서 상태와도 일치해야 한다
    assert (got == "SENSOR_FAULT") == (ts1["sensor_state"] == "SENSOR_FAULT")


def test_sensor_fault_is_checked_before_temperature():
    # 온도는 기준을 넘었지만 결측이 길다 → 설비 이상으로 판정하지 않는다
    fake = {"quality": {"longest_gap_s": 12, "flags": {"OK": 48, "GAP": 12}, "valid_ratio": 0.8}, "longest_valid_above_alarm_s": 15}
    assert et.classify_sensor_window(fake) == "SENSOR_FAULT"


def test_classify_lot_product_quality():
    rows = synth_lots("HYD-01", datetime(2027, 1, 27, 9, tzinfo=timezone.utc))
    lots = {}
    for r in rows:
        lots.setdefault(r["lot_id"], []).append(r)
    results = {lot: et.classify_lot(rs) for lot, rs in lots.items()}
    flagged = {k: v for k, v in results.items() if v}
    assert list(flagged) == ["LOT-0127-06"]
    ev = flagged["LOT-0127-06"]
    assert ev["event_type"] == "PRODUCT_QUALITY" and ev["out_of_spec"] == 5 and ev["samples"] == 5
    assert ev["is_synthetic"] is True and ev["suggestion"] == "LOT_HOLD"


def test_labels_are_not_confused():
    assert et.LABEL_KIND["profile.cooler_pct"] == "EQUIPMENT_STATE", "냉각기 상태 라벨은 제품 불량이 아니다"
    assert et.LABEL_KIND["inspection.bore_diameter"] == "PRODUCT_QUALITY"
    assert et.LABEL_KIND["observation.quality_flag"] == "SENSOR_QUALITY"


# ---- 3. 제공 화면 매핑 ----------------------------------------------------------------
def _js_map(name):
    js = (ROOT / "hydops" / "b9_dashboard" / "static" / "app.js").read_text()
    body = re.search(rf"const {name} = \{{(.*?)\}};", js).group(1)
    return dict(re.findall(r"(\w+): '([^']*)'", body))


def test_event_display_matches_dashboard():
    assert et.EVENT_DISPLAY == _js_map("TYPE_KO")


def test_typical_end_status_exists_on_dashboard():
    status_ko = _js_map("STATUS_KO")
    assert et.TYPICAL_END_STATUS == {"SENSOR_FAULT": "SENSOR_CHECK", "PRODUCT_QUALITY": "HOLD_NO_EVIDENCE"}
    assert all(v in status_ko for v in et.TYPICAL_END_STATUS.values())
