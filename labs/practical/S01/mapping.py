"""실전반 S01 · 세 센서 CSV → 공통 관측 레코드 → PostgreSQL → 최근 60초 조회 (학생 시작본 — # TODO(학생) 표시를 고친다).

B1(매핑·1초 축약) → B2(제공 품질 검사기) → B3(제공 적재·조회 함수) 경로를 학생 코드로 잇는다.
lecture/system 의 코드는 import 만 한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import islice

import numpy as np

from hydops.b2_quality.checks import SensorQualityChecker
from hydops.b3_tsdb import store
from hydops.config import DATA_DIR

RAW = DATA_DIR / "raw"
CYCLE_S = 60
# 재생 시각(ts)의 기준. 실제 수집 시각이 아니다.
# 수업 서버의 시뮬레이터가 '지금' 시각으로 관측을 쌓으므로, 그보다 이른 시각으로 재생해야
# run_id 없이 설비 최신 구간을 읽는 다른 조회를 가로채지 않는다.
LAB_REPLAY_START = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)

SENSOR_SPEC = {
    "TS1": {"file": "TS1.txt", "hz": 1, "unit": "°C"},
    "PS1": {"file": "PS1.txt", "hz": 100, "unit": "bar"},
    "FS1": {"file": "FS1.txt", "hz": 10, "unit": "L/min"},
}


def read_raw_cycle(sensor_id: str, cycle_id: int) -> np.ndarray:
    """(제공) 원본 CSV 에서 한 사이클(한 줄)을 읽는다. 줄 번호 = 사이클 번호(0부터)."""
    path = RAW / SENSOR_SPEC[sensor_id]["file"]
    with open(path) as f:
        line = next(islice(f, cycle_id, cycle_id + 1))
    return np.array(line.split("\t"), dtype=float)


def reduce_to_seconds(samples: np.ndarray, hz: int) -> list[dict]:
    """60초 × hz 샘플을 1초 단위 mean/min/max/n 60개로 축약한다."""
    if len(samples) != CYCLE_S * hz:
        raise ValueError(f"샘플 수 {len(samples)} != {CYCLE_S} x {hz}")
    shaped = samples.reshape(CYCLE_S, hz)
    # TODO(학생): 지금은 1초 구간의 첫 샘플만 골라 쓴다(솎아내기). 100 Hz 압력의 순간 변동이 사라지고
    #             원본 샘플 수도 남지 않는다. 1초 평균·최솟값·최댓값·샘플 수(n)로 축약하라.
    return [{"mean": float(sec[0]), "min": float(sec[0]), "max": float(sec[0]), "n": 1} for sec in shaped]


def map_cycle(raw: dict[str, np.ndarray], cycle_id: int, asset_id: str, replay_start: datetime) -> list[dict]:
    """한 사이클의 세 센서를 공통 관측 레코드로 바꾼다."""
    rows = []
    for sid, spec in SENSOR_SPEC.items():
        hz = spec["hz"]
        for s, st in enumerate(reduce_to_seconds(raw[sid], hz)):
            rows.append(
                {
                    "asset_id": asset_id,
                    "sensor_id": sid,
                    "ts": replay_start + timedelta(seconds=s),
                    "elapsed_s": s,
                    # TODO(학생): 원본 사이클 번호를 남기지 않으면 재생 구간이 어느 UCI 사이클인지 추적할 수 없다.
                    "origin_cycle_id": None,
                    "raw_value": st["mean"],
                    # TODO(학생): 단위를 센서마다 SENSOR_SPEC 에서 가져와라 (압력 bar, 유량 L/min).
                    "unit": "°C",
                    # TODO(학생): 1 Hz 가 아닌 센서는 {"min","max","n","source_hz"} 축약 통계를 남겨라.
                    "agg": None,
                    # TODO(학생): UCI 원본 재생은 합성 데이터가 아니다.
                    "is_synthetic": True,
                }
            )
    return rows


def load_cycles(run_id: str, cycle_ids: list[int], asset_id: str = "HYD-01", start: datetime = LAB_REPLAY_START) -> int:
    """사이클을 이어 붙여 재생하고, 제공 품질 검사기를 거쳐 PostgreSQL 에 적재한다."""
    if not run_id.startswith("LAB-"):
        raise ValueError("실습 run_id 는 LAB- 로 시작해야 한다")
    # TODO(학생): run.source 는 원본/합성 구분이다. UCI 재생은 'uci_replay' 다.
    store.create_run("simulator", "lab-s01", note="UCI 원본 재생 (ts 는 재생 시각)", run_id=run_id)
    checker = SensorQualityChecker()
    total = 0
    for i, cid in enumerate(cycle_ids):
        raw = {sid: read_raw_cycle(sid, cid) for sid in SENSOR_SPEC}
        # TODO(학생): 모든 사이클이 같은 재생 시각에서 시작해 시각이 겹친다. i 번째 사이클은 60초씩 밀어라.
        rows = map_cycle(raw, cid, asset_id, start)
        total += store.insert_observations(run_id, checker.check_many(rows))
    return total


def window_with_origin(run_id: str, asset_id: str = "HYD-01", seconds: int = 60, until: datetime | None = None) -> dict:
    """최근 구간을 조회하고 센서별로 단위·원본 사이클·위상·원본/합성 구분을 요약한다."""
    # TODO(학생): run_id 로 거르지 않으면 수업 서버 시뮬레이터가 방금 쌓은 관측(다른 run)을 읽는다.
    rows = store.recent_window(asset_id, seconds, until=until)
    sensors: dict[str, dict] = {}
    for r in rows:
        s = sensors.setdefault(
            r["sensor_id"],
            {"unit": r["unit"], "samples": 0, "origin_cycles": set(), "elapsed": [], "is_synthetic": set(), "run_ids": set()},
        )
        s["samples"] += 1
        s["origin_cycles"].add(r["origin_cycle_id"])
        s["elapsed"].append(r["elapsed_s"])
        s["is_synthetic"].add(r["is_synthetic"])
        s["run_ids"].add(r["run_id"])
    for s in sensors.values():
        s["origin_cycles"] = sorted(s["origin_cycles"], key=lambda v: (v is None, v))
        s["is_synthetic"] = sorted(s["is_synthetic"])
        s["run_ids"] = sorted(s["run_ids"])
    return {
        "asset_id": asset_id,
        "from": rows[0]["ts"] if rows else None,
        "to": rows[-1]["ts"] if rows else None,
        "sensors": sensors,
    }


def delete_lab_run(run_id: str) -> None:
    """(제공) 자기 실습 행만 지운다. 다른 run 은 건드리지 않는다."""
    if not run_id.startswith("LAB-"):
        raise ValueError("LAB- 로 시작하는 run 만 지운다")
    with store.connect() as c:
        c.execute("DELETE FROM observation WHERE run_id=%s", (run_id,))
        c.execute("DELETE FROM run WHERE run_id=%s", (run_id,))
