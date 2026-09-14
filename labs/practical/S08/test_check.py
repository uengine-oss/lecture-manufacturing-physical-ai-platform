"""S08 확인 테스트 — 재측정 판정이 '명령 성공'과 '관측 회복'을 구분하는지.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S08 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S08 -q

DB 에 쓰지 않는다. 관측은 메모리의 HydraulicSimulator → SensorQualityChecker 로 만든다(시드 7, figures F07 과 같은 조건).
"""
from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b2_quality.checks import GAP, OK, SensorQualityChecker
from hydops.b5_detect.detector import ThresholdDetector

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
spec = importlib.util.spec_from_file_location(f"s08_recovery_{BASE.name}", BASE / "recovery.py")
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)

FIG = json.loads((HERE.parents[2] / "materials" / "figures" / "figures_data.json").read_text())["outcomes"]


def closed_loop(cooling: float, dropout: tuple[int, int] | None = None, seed: int = 7, extra_s: int = 100):
    """냉각 저하 주입(t=20) → 감지 → 15초 뒤 부하 0.8 명령 → 재측정 창이 끝날 때까지 진행."""
    sim, chk, det = HydraulicSimulator("HYD-01", seed=seed), SensorQualityChecker(), ThresholdDetector()
    rows, alarm, act_at, action = [], None, None, None
    s = 0
    while act_at is None or s < act_at + extra_s:
        if s == 20:
            sim.inject_cooling_degradation(cooling)
        if dropout and s == dropout[0]:
            sim.inject_sensor_fault("dropout", dropout[1])
        if alarm is not None and s == alarm + 15 and action is None:
            res = sim.apply_load(0.8)
            act_at, action = s, {"sim_ts": sim.state.t, "command_status": "SUCCEEDED" if res["ok"] else "FAILED"}
        checked = chk.check_many(sim.step())
        rows.extend(checked)
        for r in checked:
            for sig in det.feed(r):
                if sig.event_type == "COOLING_ANOMALY" and alarm is None:
                    alarm = s
        s += 1
        assert s < 600, "감지가 일어나지 않았다"
    return rows, action


# ---------------------------------------------------------------- 시뮬레이터 세 갈래 (F07 과 같은 값)
def test_recovered_after_load_reduction():
    rows, action = closed_loop(0.4)
    r = rec.judge_recovery(rows, action)
    assert r["outcome"] == "RECOVERED"
    assert r["metrics"]["valid_ratio"] == FIG["회복 → 종결"]["valid_ratio"]
    assert r["metrics"]["longest_below_s"] == FIG["회복 → 종결"]["longest_below_s"]


def test_severe_degradation_not_improved_although_command_succeeded():
    rows, action = closed_loop(0.25)
    r = rec.judge_recovery(rows, action)
    assert action["command_status"] == "SUCCEEDED"
    assert r["outcome"] == "NOT_IMPROVED"
    assert r["metrics"]["longest_below_s"] == FIG["미개선 → 담당자 이관"]["longest_below_s"]


def test_dropout_in_window_is_insufficient_data():
    rows, action = closed_loop(0.4, dropout=(95, 45))
    r = rec.judge_recovery(rows, action)
    assert r["outcome"] == "INSUFFICIENT_DATA"
    assert r["metrics"]["valid_ratio"] == FIG["데이터 부족 → 재측정 보류"]["valid_ratio"]
    assert r["metrics"]["longest_below_s"] == FIG["데이터 부족 → 재측정 보류"]["longest_below_s"]


def test_dropout_case_next_window_recovers():
    rows, action = closed_loop(0.4, dropout=(95, 45), extra_s=160)
    r = rec.judge_recovery(rows, action, window_index=1)
    assert r["window_start"] == action["sim_ts"] + timedelta(seconds=90)
    assert r["outcome"] == "RECOVERED" and r["metrics"]["valid_ratio"] == 1.0


def test_below_alarm_but_above_recovery_is_not_improved():
    # 냉각 0.33: 부하 0.8 에서 60°C 아래로는 내려가지만 55°C 이하 10초를 채우지 못한다
    rows, action = closed_loop(0.33)
    r = rec.judge_recovery(rows, action)
    assert r["metrics"]["last_c"] < 60.0
    assert r["outcome"] == "NOT_IMPROVED"


# ---------------------------------------------------------------- 틀린 조건 하나씩 드러내는 합성 행
T0 = datetime(2027, 1, 28, 14, 0, tzinfo=timezone.utc)
ACTION = {"sim_ts": T0 + timedelta(seconds=100), "command_status": "SUCCEEDED"}


def row(sec: int, value: float | None, flag: str = OK) -> dict:
    return {"asset_id": "HYD-01", "sensor_id": "TS1", "ts": T0 + timedelta(seconds=sec), "raw_value": value, "value": value if flag == OK else None, "quality_flag": flag}


def test_pre_action_observations_are_ignored():
    before = [row(s, 45.0) for s in range(60, 100)]           # 조치 전 정상 온도 40초
    after = [row(s, 68.0) for s in range(131, 191)]           # 재측정 창(130, 190] 은 계속 68°C
    r = rec.judge_recovery(before + after, ACTION)
    assert r["outcome"] == "NOT_IMPROVED" and r["metrics"]["valid_samples"] == 60


def test_command_success_alone_is_not_recovery():
    r = rec.judge_recovery([row(s, 58.0) for s in range(131, 191)], ACTION)
    assert r["outcome"] == "NOT_IMPROVED" and r["metrics"]["longest_below_s"] == 0


def test_missing_rows_count_against_valid_ratio():
    rows = [row(s, 54.0) for s in range(131, 143)] + [row(s, 61.0) for s in range(143, 146)] + [row(s, None, GAP) for s in range(146, 191)]
    r = rec.judge_recovery(rows, ACTION)
    assert r["metrics"]["valid_ratio"] == 0.25
    assert r["outcome"] == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("window_index,start_s", [(0, 130), (1, 190)])
def test_window_position(window_index, start_s):
    start, end = rec.verify_window(ACTION, window_index=window_index)
    assert start == T0 + timedelta(seconds=start_s) and end - start == timedelta(seconds=60)
