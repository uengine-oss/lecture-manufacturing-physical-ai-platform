"""B5 · 수치 탐지 서비스.

수치 감지는 규칙과 이동 통계를 기본으로 한다. LLM 에게 센서 원시 배열을 읽혀 고장을 판정하게 하지 않는다.
- 센서 오류(품질 플래그)와 설비 이상(유효 관측의 지속 이탈)을 다른 사건으로 만든다.
- 단발 급등은 지속 조건을 채우지 못하므로 사건이 되지 않는다.
- 같은 설비·유형의 열린 사건이 있으면 새 사건을 만들지 않는다 (중복 억제).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from hydops.b2_quality.checks import BAD_FLAGS, GAP, OK, STUCK
from hydops.config import QR, TH, Thresholds


@dataclass
class Signal:
    asset_id: str
    event_type: str  # COOLING_ANOMALY / SENSOR_FAULT
    window_start: object
    window_end: object
    evidence: dict


@dataclass
class _AssetState:
    above_run: int = 0
    above_start: object = None
    above_values: list = field(default_factory=list)
    bad_run: int = 0
    bad_start: object = None
    bad_flags: dict = field(default_factory=lambda: defaultdict(int))
    recent: deque = field(default_factory=lambda: deque(maxlen=60))


class ThresholdDetector:
    """시뮬레이터 스트림용: 유효 온도 > alarm_temp 가 alarm_sustain_s 연속이면 냉각 이상."""

    def __init__(self, th: Thresholds = TH, sensor_code: str = "TS1"):
        self.th = th
        self.sensor_code = sensor_code
        self.state: dict[str, _AssetState] = defaultdict(_AssetState)

    def feed(self, row: dict) -> list[Signal]:
        if row["sensor_id"] != self.sensor_code:
            return []
        st = self.state[row["asset_id"]]
        st.recent.append(row)
        flag = row["quality_flag"]
        out: list[Signal] = []

        # 센서 오류 경로: 긴 결측(GAP)·고착(STUCK)은 센서 오류 사건
        if flag in (GAP, STUCK):
            if st.bad_run == 0:
                st.bad_start = row["ts"]
            st.bad_run += 1
            st.bad_flags[flag] += 1
            if st.bad_run == 1:
                out.append(
                    Signal(
                        row["asset_id"],
                        "SENSOR_FAULT",
                        st.bad_start,
                        row["ts"],
                        {
                            "rule": "quality-gap-stuck-v1",
                            "flag": flag,
                            "gap_hold_s": QR.gap_hold_s,
                            "stuck_run": QR.stuck_run,
                            "note": "센서 오류 — 설비 조치 보류, 센서 점검 제안",
                        },
                    )
                )
        elif flag == OK:
            st.bad_run = 0
            st.bad_flags = defaultdict(int)

        # 설비 이상 경로: 유효 관측만 센다. 품질 불량 관측은 세지 않지만(건너뜀) GAP 이면 지속 판단을 초기화
        if flag == OK and row["value"] is not None and row["value"] > self.th.alarm_temp_c:
            if st.above_run == 0:
                st.above_start = row["ts"]
                st.above_values = []
            st.above_run += 1
            st.above_values.append(row["value"])
            if st.above_run == self.th.alarm_sustain_s:
                vals = st.above_values
                out.append(
                    Signal(
                        row["asset_id"],
                        "COOLING_ANOMALY",
                        st.above_start,
                        row["ts"],
                        {
                            "rule": self.th.rule_version,
                            "sensor": self.sensor_code,
                            "threshold_c": self.th.alarm_temp_c,
                            "sustain_s": self.th.alarm_sustain_s,
                            "valid_samples": len(vals),
                            "mean_c": round(sum(vals) / len(vals), 2),
                            "max_c": round(max(vals), 2),
                        },
                    )
                )
        elif flag == OK or flag == GAP:
            st.above_run = 0
        # MISSING/SPIKE 단발은 지속 카운터를 유지 (세지도 초기화하지도 않음)
        return out


CURRENT_S = 15


def recent_summary(rows: list[dict], th: Thresholds = TH) -> dict:
    """get_recent_window 도구가 LLM 에 넘기는 요약. 원시 배열 대신 코드가 계산한 통계만 준다."""
    from hydops.b2_quality.checks import window_quality

    by_sensor: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sensor[r["sensor_id"]].append(r)
    out = {}
    for sid, rs in by_sensor.items():
        vals = [r["value"] for r in rs if r["quality_flag"] == OK and r["value"] is not None]
        q = window_quality(rs)
        s = {
            "unit": rs[0]["unit"],
            "samples": len(rs),
            "quality": q,
            "valid_mean": round(sum(vals) / len(vals), 2) if vals else None,
            "valid_min": round(min(vals), 2) if vals else None,
            "valid_max": round(max(vals), 2) if vals else None,
            "last_valid": round(vals[-1], 2) if vals else None,
            "from": rs[0]["ts"],
            "to": rs[-1]["ts"],
        }
        if sid == "TS1":
            run = best = 0
            for r in rs:
                if r["quality_flag"] == OK and r["value"] is not None and r["value"] > th.alarm_temp_c:
                    run += 1
                    best = max(best, run)
                elif r["quality_flag"] == OK:
                    run = 0
            s["longest_valid_above_alarm_s"] = best
            s["sustained_anomaly"] = best >= th.alarm_sustain_s
            # 현재 센서 상태는 최근 15초로 판단한다. 창 앞부분에서 이미 끝난 결측·고착은 설비 판단을 막지 않고 따로 알린다.
            tail = rs[-CURRENT_S:]
            tq = window_quality(tail)
            now_fault = tq["longest_gap_s"] >= QR.gap_hold_s or tq["flags"].get(STUCK, 0) > 0 or tq["valid_ratio"] < 0.7
            earlier = q["longest_gap_s"] >= QR.gap_hold_s or q["flags"].get(STUCK, 0) > 0 or q["valid_ratio"] < 0.7
            s["sensor_state"] = "SENSOR_FAULT" if now_fault else "VALID"
            s["current_quality"] = {"last_s": len(tail), "valid_ratio": tq["valid_ratio"], "flags": tq["flags"]}
            s["quality_issue_earlier_in_window"] = bool(earlier and not now_fault)
        out[sid] = s
    return out


# ---- UCI 재생 데이터용: 정상 위상 기준 + 이동 통계 --------------------------------
@dataclass
class PhaseBaseline:
    mean: list  # elapsed_s 별 평균
    std: list
    cycles: list

    @classmethod
    def fit(cls, temps, cycle_ids):
        import numpy as np

        arr = temps[cycle_ids]
        return cls(mean=arr.mean(axis=0).tolist(), std=np.maximum(arr.std(axis=0), 0.2).tolist(), cycles=list(map(int, cycle_ids)))


def detect_cycle_phase(values, baseline: PhaseBaseline, k_sigma: float = 4.0, min_delta_c: float = 3.0, sustain_s: int = 10, smooth_s: int = 5) -> dict:
    """한 사이클의 온도를 같은 위상의 정상 기준과 비교한다.

    잔차 = 이동평균(값) - 기준평균(위상). 잔차 > max(kσ, min_delta) 가 sustain_s 연속이면 이상.
    반환: is_anomaly, first_alarm_s (감지 지연), max_residual
    """
    import numpy as np

    v = np.asarray(values, dtype=float)
    ma = np.convolve(v, np.ones(smooth_s) / smooth_s, mode="full")[: len(v)]
    ma[: smooth_s - 1] = [v[: i + 1].mean() for i in range(smooth_s - 1)]
    resid = ma - np.asarray(baseline.mean)
    limit = np.maximum(k_sigma * np.asarray(baseline.std), min_delta_c)
    above = resid > limit
    run = 0
    first = None
    for i, a in enumerate(above):
        run = run + 1 if a else 0
        if run >= sustain_s and first is None:
            first = i
    return {"is_anomaly": first is not None, "first_alarm_s": first, "max_residual": float(resid.max()), "residual": resid.tolist(), "limit": limit.tolist()}
