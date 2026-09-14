"""실전반 S02 · 노이즈를 구별하는 수집 블록 (정답본).

lecture/system/hydops/b2_quality/checks.py 의 검사기를 실습용으로 복사해 네 곳을 고친다.
1. aggregate_1s        — 고주파 센서의 1초 집계에서 결측 샘플을 0 으로 채우지 않는다
2. LabQualityChecker   — 긴 결측(GAP) 판정 보류 · 고착(STUCK) 기준 · 급등(SPIKE)과 수준 변화 구분
3. store_checked       — 원시 값 · 정제 값 · 품질 플래그를 함께 저장한다
4. window_state        — 센서 오류와 설비 이상을 다른 상태로 표시한다
"""
from __future__ import annotations

from collections import defaultdict, deque

import numpy as np

from hydops.b2_quality.checks import GAP, MISSING, OK, OUT_OF_RANGE, SPIKE, STUCK, window_quality
from hydops.b3_tsdb import store
from hydops.config import QR, TH, QualityRules


# ---- 1. 1초 집계 ---------------------------------------------------------------
def aggregate_1s(samples: np.ndarray, hz: int, min_valid_ratio: float = 0.5) -> list[dict]:
    """60초 × hz 샘플(결측은 NaN)을 1초 단위로 집계한다.

    유효 샘플만 평균하고 n 에 유효 샘플 수를 남긴다. 유효 샘플이 hz × min_valid_ratio 보다 적으면
    그 1초는 값이 없는 것(mean=None)으로 둔다 — 뒤의 품질 검사가 MISSING/GAP 으로 판정한다.
    """
    shaped = np.asarray(samples, dtype=float).reshape(-1, hz)
    out = []
    for sec in shaped:
        valid = sec[~np.isnan(sec)]
        n = int(valid.size)
        if n < hz * min_valid_ratio:
            out.append({"mean": None, "min": None, "max": None, "n": n})
        else:
            out.append({"mean": float(valid.mean()), "min": float(valid.min()), "max": float(valid.max()), "n": n})
    return out


# ---- 2. 품질 검사기 -------------------------------------------------------------
class LabQualityChecker:
    """센서별 상태를 기억하는 스트리밍 검사기 (실습용 복사본)."""

    def __init__(self, rules: QualityRules = QR):
        self.rules = rules
        self._recent = defaultdict(lambda: deque(maxlen=rules.spike_window))  # 최근 유효 값
        self._last_raw: dict = {}
        self._same_run = defaultdict(int)
        self._missing_run = defaultdict(int)
        self._spike_run = defaultdict(int)

    def check(self, row: dict) -> dict:
        key = (row["asset_id"], row["sensor_id"])
        sid = row["sensor_id"]
        raw = row.get("raw_value")
        flag = OK

        if raw is None:
            self._missing_run[key] += 1
            # 짧은 결측은 MISSING, gap_hold_s 이상 이어지면 GAP (판정 보류 신호). 값을 채워 넣지 않는다.
            flag = GAP if self._missing_run[key] >= self.rules.gap_hold_s else MISSING
            self._same_run[key] = 0
        else:
            self._missing_run[key] = 0
            lo = self.rules.physical_min.get(sid, float("-inf"))
            hi = self.rules.physical_max.get(sid, float("inf"))
            if raw < lo or raw > hi:
                flag = OUT_OF_RANGE
            else:
                if self._last_raw.get(key) is not None and raw == self._last_raw[key]:
                    self._same_run[key] += 1
                else:
                    self._same_run[key] = 1
                recent = self._recent[key]
                if self._same_run[key] >= self.rules.stuck_run:
                    # 같은 값이 stuck_run 번째 반복되는 순간부터 STUCK
                    flag = STUCK
                elif recent and abs(raw - recent[-1]) > self.rules.spike_delta.get(sid, float("inf")):
                    # 직전 유효값과 1초 사이 점프가 기준을 넘으면 급등. 3회 연속이면 수준 변화로 받아들인다
                    self._spike_run[key] += 1
                    flag = SPIKE if self._spike_run[key] < 3 else OK
            self._last_raw[key] = raw
            if flag != SPIKE:
                self._spike_run[key] = 0
            if flag == OK:
                self._recent[key].append(raw)

        return {**row, "quality_flag": flag, "value": raw if flag == OK else None}

    def check_many(self, rows: list[dict]) -> list[dict]:
        return [self.check(r) for r in sorted(rows, key=lambda r: (r["ts"], r["sensor_id"]))]


# ---- 3. 저장 --------------------------------------------------------------------
def store_checked(run_id: str, rows: list[dict], source: str = "uci_replay", scenario: str = "lab-s02") -> int:
    """검사한 관측을 원시 값(raw_value)·정제 값(value)·품질 플래그(quality_flag)와 함께 저장한다."""
    if not run_id.startswith("LAB-"):
        raise ValueError("실습 run_id 는 LAB- 로 시작해야 한다")
    store.create_run(source, scenario, note="S02 품질 검사 실습", run_id=run_id)
    return store.insert_observations(run_id, rows)


# ---- 4. 구간 상태 ----------------------------------------------------------------
SENSOR_FAULT, EQUIPMENT_ANOMALY, NORMAL, NO_DATA = "SENSOR_FAULT", "EQUIPMENT_ANOMALY", "NORMAL", "NO_DATA"


def window_state(rows: list[dict], rules: QualityRules = QR, alarm_c: float = TH.alarm_temp_c, sustain_s: int = TH.alarm_sustain_s) -> dict:
    """한 센서(TS1)의 구간을 센서 오류 / 설비 이상 / 정상 중 하나로 표시한다.

    센서 오류 조건을 먼저 본다: 센서를 믿을 수 없으면 설비 이상 판정을 보류한다.
    설비 이상은 품질이 OK 인 정제 값(value)만으로 센다.
    """
    q = window_quality(rows)
    if q["n"] == 0:
        return {"state": NO_DATA, "quality": q, "longest_valid_above_s": 0}
    run = best = 0
    for r in rows:
        if r["quality_flag"] == OK and r["value"] is not None and r["value"] > alarm_c:
            run += 1
            best = max(best, run)
        elif r["quality_flag"] == OK:
            run = 0
    if q["longest_gap_s"] >= rules.gap_hold_s or q["flags"].get(STUCK, 0) > 0 or q["valid_ratio"] < 0.7:
        state = SENSOR_FAULT
    elif best >= sustain_s:
        state = EQUIPMENT_ANOMALY
    else:
        state = NORMAL
    return {"state": state, "quality": q, "longest_valid_above_s": best}


def delete_lab_run(run_id: str) -> None:
    """(제공) 자기 실습 행만 지운다."""
    if not run_id.startswith("LAB-"):
        raise ValueError("LAB- 로 시작하는 run 만 지운다")
    with store.connect() as c:
        c.execute("DELETE FROM observation WHERE run_id=%s", (run_id,))
        c.execute("DELETE FROM run WHERE run_id=%s", (run_id,))
