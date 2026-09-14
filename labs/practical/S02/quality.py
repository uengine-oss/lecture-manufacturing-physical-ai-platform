"""실전반 S02 · 노이즈를 구별하는 수집 블록 (학생 시작본 — # TODO(학생) 표시를 고친다).

lecture/system/hydops/b2_quality/checks.py 의 검사기를 실습용으로 복사해 네 곳을 고친다.
1. aggregate_1s        — 고주파 센서의 1초 집계에서 결측 샘플을 0 으로 채우지 않는다
2. LabQualityChecker   — 긴 결측(GAP) 판정 보류 · 고착(STUCK) 기준 · 급등(SPIKE)과 수준 변화 구분
3. store_checked       — 원시 값 · 정제 값 · 품질 플래그를 함께 저장한다
4. window_state        — 센서 오류와 설비 이상을 다른 상태로 표시한다
"""
from __future__ import annotations

import statistics
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
        # TODO(학생): 결측 샘플(NaN)을 0 으로 채우고 n 을 hz 로 고정한다. 결측이 평균을 끌어내리고
        #             유효 샘플 수도 사라진다. 유효 샘플만 집계하고, 너무 적으면 mean=None 으로 두어라.
        filled = np.nan_to_num(sec, nan=0.0)
        out.append({"mean": float(filled.mean()), "min": float(filled.min()), "max": float(filled.max()), "n": hz})
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
            # TODO(학생): 결측이 아무리 길어도 MISSING 이고, 정제 값을 직전 유효값으로 채운다(forward fill).
            #             gap_hold_s 이상 이어지면 GAP 으로 판정을 보류하고, 결측 관측의 정제 값은 비워라.
            flag = MISSING
            self._same_run[key] = 0
            recent = self._recent[key]
            return {**row, "quality_flag": flag, "value": recent[-1] if recent else None}
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
                # TODO(학생): 기준은 "같은 값이 stuck_run(8)번째 반복되는 순간부터 STUCK" 이다. 비교 연산을 확인하라.
                if self._same_run[key] > self.rules.stuck_run:
                    flag = STUCK
                # TODO(학생): 최근 유효값들의 중앙값과 비교하고 수준 변화를 받아들이지 않는다. 온도가 빠르게 오르면
                #             중앙값이 뒤처져 모든 값이 SPIKE 로 막힌다. 직전 유효값과 비교하고 3회 연속이면 OK 로 받아들여라.
                elif recent and abs(raw - statistics.median(recent)) > self.rules.spike_delta.get(sid, float("inf")):
                    self._spike_run[key] += 1
                    flag = SPIKE
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
    # TODO(학생): 정제 값만 남기려고 원시 값을 덮어쓴다. 원시 값은 그대로 보존해야 나중에 센서 오류를 다시 검토할 수 있다.
    rows = [{**r, "raw_value": r.get("value")} for r in rows]
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
        # TODO(학생): 원시 값으로 센다. 고착·급등 값도 경보 온도 위에 있으면 설비 이상으로 세어진다. 품질 OK 인 정제 값만 세라.
        if r["raw_value"] is not None and r["raw_value"] > alarm_c:
            run += 1
            best = max(best, run)
        else:
            run = 0
    # TODO(학생): 설비 이상을 먼저 판정한다. 센서를 믿을 수 없는 구간은 설비 이상 판정을 보류해야 한다(순서를 바꿔라).
    if best >= sustain_s:
        state = EQUIPMENT_ANOMALY
    elif q["flags"].get(STUCK, 0) > 0 or q["valid_ratio"] < 0.7:
        state = SENSOR_FAULT
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
