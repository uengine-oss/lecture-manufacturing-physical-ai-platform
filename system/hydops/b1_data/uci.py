"""B1 · UCI 유압설비 데이터를 공통 관측 형식으로 매핑한다.

- TS1: 온도 1 Hz, °C → 초 단위 값 그대로 (위상 elapsed_s 보존)
- PS1: 압력 100 Hz, bar → 1초 평균·최솟값·최댓값으로 축약
- FS1: 유량 10 Hz, L/min → 1초 평균으로 축약하고 원본 샘플 수(n) 추적
- profile: 냉각기 상태·안정 상태 → 정답 평가에만 사용하고 탐지 입력에서 제외
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from hydops.config import DATA_DIR

RAW = DATA_DIR / "raw"
CYCLE_S = 60

# 센서 매핑 표 (통합반 1회차 실습에서 학생이 채우는 표와 같은 내용)
SENSOR_MAP = {
    "TS1": {"file": "TS1.txt", "hz": 1, "unit": "°C", "quantity": "temperature"},
    "PS1": {"file": "PS1.txt", "hz": 100, "unit": "bar", "quantity": "pressure"},
    "FS1": {"file": "FS1.txt", "hz": 10, "unit": "L/min", "quantity": "flow"},
}
PROFILE_COLS = ["cooler_pct", "valve_pct", "pump_leak", "accumulator_bar", "stable_flag"]


def load_profile() -> pd.DataFrame:
    df = pd.read_csv(RAW / "profile.txt", sep="\t", header=None, names=PROFILE_COLS)
    df.index.name = "origin_cycle_id"
    # UCI 문서: stable_flag 0 = 안정 상태 도달, 1 = 아직 안정되지 않았을 수 있음
    df["is_stable"] = df["stable_flag"] == 0
    return df


def load_sensor_matrix(sensor_id: str) -> np.ndarray:
    meta = SENSOR_MAP[sensor_id]
    return pd.read_csv(RAW / meta["file"], sep="\t", header=None).to_numpy(dtype=float)


def reduce_to_1s(matrix: np.ndarray, hz: int) -> dict[str, np.ndarray]:
    """(cycles, 60*hz) → 1초 단위 mean/min/max/n (cycles, 60)."""
    cycles = matrix.shape[0]
    shaped = matrix.reshape(cycles, CYCLE_S, hz)
    return {
        "mean": shaped.mean(axis=2),
        "min": shaped.min(axis=2),
        "max": shaped.max(axis=2),
        "n": np.full((cycles, CYCLE_S), hz),
    }


@dataclass
class ReducedDataset:
    """축약본: 사이클 × 60초 × 센서. 강사가 미리 만들어 제공하는 파일."""

    sensors: dict[str, dict[str, np.ndarray]]
    profile: pd.DataFrame


def build_reduced() -> ReducedDataset:
    sensors = {}
    for sid, meta in SENSOR_MAP.items():
        sensors[sid] = reduce_to_1s(load_sensor_matrix(sid), meta["hz"])
    return ReducedDataset(sensors=sensors, profile=load_profile())


def save_reduced(ds: ReducedDataset) -> None:
    out = DATA_DIR / "reduced"
    out.mkdir(parents=True, exist_ok=True)
    arrays = {f"{sid}_{k}": v for sid, d in ds.sensors.items() for k, v in d.items()}
    np.savez_compressed(out / "hydraulic_1s.npz", **arrays)
    ds.profile.to_csv(out / "profile.csv")


def load_reduced() -> ReducedDataset:
    path = DATA_DIR / "reduced" / "hydraulic_1s.npz"
    if not path.exists():
        ds = build_reduced()
        save_reduced(ds)
        return ds
    z = np.load(path)
    sensors: dict[str, dict[str, np.ndarray]] = {}
    for key in z.files:
        sid, stat = key.split("_", 1)
        sensors.setdefault(sid, {})[stat] = z[key]
    profile = pd.read_csv(DATA_DIR / "reduced" / "profile.csv", index_col="origin_cycle_id")
    return ReducedDataset(sensors=sensors, profile=profile)


def cycle_observations(
    ds: ReducedDataset,
    cycle_id: int,
    asset_id: str,
    replay_start: datetime,
) -> list[dict]:
    """한 사이클을 공통 관측 레코드 목록으로 바꾼다.

    replay_ts 는 재생 시각이다. 실제 수집 시각으로 오인하지 않도록 origin_cycle_id·elapsed_s 를 함께 둔다.
    """
    rows = []
    for sid, meta in SENSOR_MAP.items():
        stats = ds.sensors[sid]
        for s in range(CYCLE_S):
            mean = float(stats["mean"][cycle_id, s])
            rows.append(
                {
                    "asset_id": asset_id,
                    "sensor_id": sid,
                    "ts": replay_start + timedelta(seconds=s),
                    "elapsed_s": s,
                    "origin_cycle_id": int(cycle_id),
                    "raw_value": mean,
                    "unit": meta["unit"],
                    "agg": None
                    if meta["hz"] == 1
                    else {
                        "min": round(float(stats["min"][cycle_id, s]), 4),
                        "max": round(float(stats["max"][cycle_id, s]), 4),
                        "n": int(stats["n"][cycle_id, s]),
                        "source_hz": meta["hz"],
                    },
                    "is_synthetic": False,
                }
            )
    return rows


def replay_cycles(ds: ReducedDataset, cycle_ids: list[int], asset_id: str, start: datetime | None = None):
    """제공 재생기: 사이클을 이어 붙여 재생한다. 원본 CSV 재생은 조치에 반응하지 않는다."""
    start = start or datetime(2026, 10, 31, 14, 0, tzinfo=timezone.utc)
    for i, cid in enumerate(cycle_ids):
        yield cid, cycle_observations(ds, cid, asset_id, start + timedelta(seconds=i * CYCLE_S))


def inject_sensor_errors(rows: list[dict], sensor_id: str = "TS1", seed: int = 7) -> list[dict]:
    """오류 주입본: 결측·급등·고착을 섞는다 (통합반 2회차 '오류 주입본')."""
    rng = np.random.default_rng(seed)
    target = [r for r in rows if r["sensor_id"] == sensor_id]
    target.sort(key=lambda r: r["ts"])
    n = len(target)
    # 급등 1건
    k = int(rng.integers(5, n // 3))
    target[k]["raw_value"] = target[k]["raw_value"] + 25.0
    # 결측 7초 (긴 결측)
    k = int(rng.integers(n // 3, n // 2))
    for r in target[k : k + 7]:
        r["raw_value"] = None
    # 고착 10초
    k = int(rng.integers(n // 2 + 5, n - 12))
    v = target[k]["raw_value"]
    for r in target[k : k + 10]:
        r["raw_value"] = v
    return rows
