"""B2 · 센서 품질 검사.

센서 오류(결측·급등·고착·범위 이탈)와 설비 이상을 구분하기 위해 관측마다 품질 플래그를 붙인다.
원시 값(raw_value)은 그대로 보존하고, 정제 값(value)은 품질이 OK 일 때만 채운다.
긴 결측을 보간해서 정상 값처럼 숨기지 않는다.
"""
from __future__ import annotations

from collections import defaultdict, deque

from hydops.config import QR, QualityRules

OK, MISSING, GAP, SPIKE, STUCK, OUT_OF_RANGE = "OK", "MISSING", "GAP", "SPIKE", "STUCK", "OUT_OF_RANGE"
BAD_FLAGS = {MISSING, GAP, SPIKE, STUCK, OUT_OF_RANGE}


class SensorQualityChecker:
    """센서별 상태를 기억하는 스트리밍 검사기. 재생기·시뮬레이터 모두 같은 검사기를 쓴다."""

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
            # 짧은 결측은 MISSING, 기준 이상 이어지면 GAP (판정 보류 신호)
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
                    flag = STUCK
                elif recent and abs(raw - recent[-1]) > self.rules.spike_delta.get(sid, float("inf")):
                    # 1초 사이에 물리적으로 불가능한 점프 → 급등. 단, 3회 이상 연속이면 수준 변화로 받아들인다
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


def window_quality(rows: list[dict]) -> dict:
    """구간 품질 요약: 유효 비율, 플래그 분포, 최장 결측."""
    n = len(rows)
    counts: dict[str, int] = defaultdict(int)
    longest_gap = run = 0
    for r in rows:
        counts[r["quality_flag"]] += 1
        if r["quality_flag"] in (MISSING, GAP):
            run += 1
            longest_gap = max(longest_gap, run)
        else:
            run = 0
    valid = counts.get(OK, 0)
    return {
        "n": n,
        "valid": valid,
        "valid_ratio": round(valid / n, 3) if n else 0.0,
        "flags": dict(counts),
        "longest_gap_s": longest_gap,
    }


def classify_window(rows: list[dict], rules: QualityRules = QR) -> str:
    """구간이 '센서 오류'인지 판단한다. 센서 오류면 설비 조치를 보류한다."""
    q = window_quality(rows)
    if q["n"] == 0:
        return "NO_DATA"
    if q["longest_gap_s"] >= rules.gap_hold_s or q["flags"].get(STUCK, 0) > 0:
        return "SENSOR_FAULT"
    if q["valid_ratio"] < 0.7:
        return "SENSOR_FAULT"
    return "VALID"
