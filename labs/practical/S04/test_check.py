"""실전반 S04 확인 테스트 — 지속 조건·중복 억제·고정 시험 구간·지속 조건 비교.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S04 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S04 -q

DB·Neo4j·서버에 쓰지 않는다. 시뮬레이터와 UCI 축약본만 메모리에서 쓴다.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("HYDOPS_AGENT_MODE", "offline")

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE


def _load(name: str):
    mod_name = f"lab_s04_{name}_{'solution' if BASE.name == 'solution' else 'student'}"
    spec = importlib.util.spec_from_file_location(mod_name, BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load("detector_lab")
T0 = datetime(2026, 11, 28, 14, 0, tzinfo=timezone.utc)


def _rows(spec: list[tuple[str, float | None]]) -> list[dict]:
    """(플래그, 원시값) 목록 → 품질 검사를 거친 모양의 관측 행."""
    out = []
    for i, (flag, raw) in enumerate(spec):
        out.append({"asset_id": "HYD-01", "sensor_id": "TS1", "ts": T0 + timedelta(seconds=i), "raw_value": raw, "value": raw if flag == "OK" else None, "quality_flag": flag, "unit": "°C"})
    return out


def _signals(rows, sustain_s=10):
    d = L.SustainDetector(sustain_s=sustain_s)
    out = []
    for r in rows:
        out.extend(d.feed(r))
    return out


# ---- 1. 지속 조건 -----------------------------------------------------------------
def test_short_missing_does_not_reset_sustain():
    rows = _rows([("OK", 65.0)] * 6 + [("MISSING", None)] + [("OK", 65.0)] * 4)
    sig = _signals(rows)
    assert len(sig) == 1, "짧은 결측(MISSING) 1초 때문에 지속 카운터가 초기화되면 안 된다"
    assert sig[0]["valid_samples"] == 10
    assert sig[0]["window_start"] == T0 and sig[0]["window_end"] == T0 + timedelta(seconds=10)


def test_spike_is_not_counted_as_valid():
    rows = _rows([("OK", 65.0)] * 9 + [("SPIKE", 95.0)])
    assert _signals(rows) == [], "SPIKE 원시값은 유효 관측이 아니므로 세지 않는다"
    rows = _rows([("SPIKE", 95.0)] + [("OK", 20.0)] * 3)
    assert _signals(rows, sustain_s=1) == [], "지속 1초여도 급등 원시값으로 경보를 내면 안 된다"


def test_valid_low_value_and_gap_reset():
    assert _signals(_rows([("OK", 65.0)] * 9 + [("OK", 55.0)] + [("OK", 65.0)] * 9)) == []
    gap = [("MISSING", None)] * 4 + [("GAP", None)]
    assert _signals(_rows([("OK", 65.0)] * 5 + gap + [("OK", 65.0)] * 5)) == []


def test_matches_system_detector_on_simulator_stream():
    """정답 기준: 시스템의 ThresholdDetector 와 같은 시각에 같은 수의 신호를 낸다."""
    from hydops.b5_detect.detector import ThresholdDetector

    rows = L.simulate_rows(150, 0.4, seed=7, degrade_at=30, dropout_at=47, dropout_s=2)
    sys_det = ThresholdDetector()
    expected = [(s.window_start, s.window_end) for r in rows for s in sys_det.feed(r) if s.event_type == "COOLING_ANOMALY"]
    got = [(s["window_start"], s["window_end"]) for s in _signals(rows)]
    assert got == expected and len(expected) == 1


# ---- 2. 중복 억제 -----------------------------------------------------------------
def test_event_book_suppresses_open_duplicates():
    book = L.EventBook()
    sig = {"asset_id": "HYD-01", "event_type": "COOLING_ANOMALY", "window_start": T0, "window_end": T0}
    ev1, c1 = book.create(sig)
    ev2, c2 = book.create(sig)
    assert c1 is True and c2 is False and ev2["event_id"] == ev1["event_id"]
    assert ev1["suppressed"] == 1
    other, c3 = book.create({**sig, "asset_id": "HYD-02"})
    assert c3 is True and other["event_id"] != ev1["event_id"]
    book.set_status(ev1["event_id"], "CLOSED")
    ev4, c4 = book.create(sig)
    assert c4 is True and ev4["event_id"] != ev1["event_id"], "닫힌 사건 뒤의 새 신호는 새 사건이 된다"


def test_boundary_stream_makes_one_event():
    rows = L.simulate_rows(300, 0.5, seed=7)  # 정상 상태 온도가 60°C 경계에 머문다
    res = L.run_stream(rows, L.SustainDetector(sustain_s=1), L.EventBook())
    assert res["signals"] > 1
    assert res["events_created"] == 1 and res["suppressed"] == res["signals"] - 1


# ---- 3·4. 고정 시험 구간과 지속 조건 비교 ------------------------------------------
def test_test_split_is_fixed():
    from hydops.b5_detect import evaluate as E

    a, b = L.fixed_test_ids(), L.fixed_test_ids()
    assert a == b == list(E.fixed_split()[2])
    assert len(a) == 180


@pytest.fixture(scope="module")
def table():
    return L.compare_sustain((1, 10, 20))


def test_compare_sustain_uses_same_split_and_params(table):
    from hydops.b5_detect import evaluate as E

    for row in table:
        ref = E.evaluate(sustain_s=row["sustain_s"])
        for k in ("tp", "fp", "fn", "tn", "mean_delay_s"):
            assert row[k] == ref[k], f"sustain_s={row['sustain_s']} 의 {k} 가 evaluate(sustain_s=...) 와 다르다"


def test_compare_sustain_shows_delay_tradeoff(table):
    by = {r["sustain_s"]: r for r in table}
    assert by[10]["tp"] + by[10]["fn"] == 120 and by[10]["fp"] + by[10]["tn"] == 60
    assert by[1]["mean_delay_s"] < by[10]["mean_delay_s"] < by[20]["mean_delay_s"]
    assert by[10]["fp"] == 1 and by[10]["fp_cycles"] == [1467]
