"""통합반 S02 점검 — 품질 기준 빈칸, 최근 60초 SQL 빈칸, 정상·보류 구간 빈칸.

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S02 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
DB 에는 run_id 가 LAB-S02- 로 시작하는 행만 쓰고 테스트가 끝나면 그 행만 지운다.
"""
import importlib.util
import os
from pathlib import Path

import pytest

from hydops.b2_quality.checks import classify_window
from hydops.b3_tsdb import store
from hydops.config import QR

HERE = Path(__file__).resolve().parent
SRC = (HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE) / "quality_lab.py"


def _load():
    spec = importlib.util.spec_from_file_location("s02_quality_lab", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab = _load()


def test_rules_match_system_rules():
    assert lab.RULES.gap_hold_s == QR.gap_hold_s, "[빈칸 1] gap_hold_s"
    assert lab.RULES.stuck_run == QR.stuck_run, "[빈칸 1] stuck_run"
    assert lab.RULES.spike_delta["TS1"] == QR.spike_delta["TS1"], "[빈칸 1] spike_delta TS1"


def test_injected_cycle_flags():
    checked = lab.check_rows(lab.make_injected_rows())
    assert lab.flag_counts(checked) == {"OK": 49, "SPIKE": 1, "MISSING": 4, "GAP": 3, "STUCK": 3}
    ts1 = [r for r in checked if r["sensor_id"] == "TS1"]
    # 품질이 나쁜 관측은 정제 값(value)을 비우고, 원시 값은 보존한다
    assert all(r["value"] is None for r in ts1 if r["quality_flag"] != "OK")
    assert any(r["raw_value"] is not None for r in ts1 if r["quality_flag"] == "STUCK")


@pytest.fixture()
def loaded_run():
    checked = lab.check_rows(lab.make_injected_rows())
    run_id = lab.new_run_id()
    assert run_id.startswith("LAB-")
    lab.load_to_db(run_id, checked)
    try:
        yield run_id
    finally:
        with store.connect() as c:
            c.execute("DELETE FROM observation WHERE run_id = %s", (run_id,))
            c.execute("DELETE FROM run WHERE run_id = %s", (run_id,))


def test_last_60s_query(loaded_run):
    rows = lab.last_60s(loaded_run)
    assert len(rows) == 60, "[빈칸 2] 최근 60초면 TS1 60행"
    assert "quality_flag" in rows[0] and "origin_cycle_id" in rows[0], "[빈칸 2] 꺼낼 열"
    assert {r["origin_cycle_id"] for r in rows} == {1500}
    flags = [r["quality_flag"] for r in rows]
    assert flags.count("GAP") == 3 and flags.count("STUCK") == 3
    assert classify_window(rows) == "SENSOR_FAULT"


def test_normal_and_hold_ranges(loaded_run):
    for rng in (lab.NORMAL_RANGE, lab.HOLD_RANGE):
        assert all(isinstance(x, int) for x in rng) and 0 <= rng[0] <= rng[1] <= 59, "[빈칸 3] 0~59 사이 정수 (처음, 끝)"
    normal = lab.range_rows(loaded_run, lab.NORMAL_RANGE)
    hold = lab.range_rows(loaded_run, lab.HOLD_RANGE)
    assert len(normal) >= 5 and len(hold) >= 5, "[빈칸 3] 구간은 5초 이상"
    assert classify_window(normal) == "VALID"
    assert classify_window(hold) == "SENSOR_FAULT"


def test_cleanup_removes_only_my_rows():
    checked = lab.check_rows(lab.make_injected_rows())
    run_id = lab.new_run_id()
    lab.load_to_db(run_id, checked)
    assert lab.cleanup(run_id) == 0
    with store.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM run WHERE run_id = %s", (run_id,)).fetchone()["n"] == 0
