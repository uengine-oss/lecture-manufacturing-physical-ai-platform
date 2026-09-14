"""S04 · 지속 조건·중복 억제·고정 시험 구간 (정답본).

원본: lecture/system/hydops/b5_detect/detector.py (ThresholdDetector 의 설비 이상 경로),
      hydops/b3_tsdb/store.py (create_event 의 열린 사건 중복 억제),
      hydops/b5_detect/evaluate.py (fixed_split, evaluate).
시스템 코드는 고치지 않는다. 필요한 부분만 이 파일로 옮겨 변형했다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b2_quality.checks import GAP, OK, SensorQualityChecker
from hydops.b5_detect import evaluate as E

# store.open_event 가 '닫힌 사건'으로 보는 상태 (같은 목록)
CLOSED_STATUSES = {"CLOSED", "ESCALATED", "REJECTED", "HOLD_NO_EVIDENCE", "SENSOR_CHECK", "RUN_ENDED"}


# ---- 1. 지속 조건 ---------------------------------------------------------------
@dataclass
class _Run:
    count: int = 0
    start: object = None
    values: list = field(default_factory=list)


class SustainDetector:
    """유효 온도 > threshold_c 가 sustain_s 번 연속이면 COOLING_ANOMALY 신호를 낸다."""

    def __init__(self, threshold_c: float = 60.0, sustain_s: int = 10, sensor_code: str = "TS1"):
        self.threshold_c = threshold_c
        self.sustain_s = sustain_s
        self.sensor_code = sensor_code
        self.runs: dict[str, _Run] = {}

    def feed(self, row: dict) -> list[dict]:
        if row["sensor_id"] != self.sensor_code:
            return []
        st = self.runs.setdefault(row["asset_id"], _Run())
        flag = row["quality_flag"]
        value = row.get("value")

        # 품질 OK 인 정제 값(value)만 센다. raw_value 는 급등·고착 값이 섞여 있다.
        if flag == OK and value is not None and value > self.threshold_c:
            if st.count == 0:
                st.start = row["ts"]
                st.values = []
            st.count += 1
            st.values.append(value)
            if st.count == self.sustain_s:
                return [
                    {
                        "asset_id": row["asset_id"],
                        "event_type": "COOLING_ANOMALY",
                        "window_start": st.start,
                        "window_end": row["ts"],
                        "valid_samples": len(st.values),
                        "mean_c": round(sum(st.values) / len(st.values), 2),
                    }
                ]
        elif flag == OK or flag == GAP:
            # 유효 관측이 기준 이하이거나, 긴 결측(GAP)이면 지속 판단을 처음부터 다시 한다
            st.count = 0
        # MISSING·SPIKE 단발: 세지도 초기화하지도 않는다
        return []


# ---- 2. 중복 억제 ---------------------------------------------------------------
class EventBook:
    """store.create_event 의 '설비·유형당 열린 사건 하나' 규칙을 메모리에서 재현한다 (DB 에 쓰지 않는다)."""

    def __init__(self):
        self.events: list[dict] = []

    def open_event(self, asset_id: str, event_type: str) -> dict | None:
        for ev in self.events:
            if ev["asset_id"] == asset_id and ev["event_type"] == event_type and ev["status"] not in CLOSED_STATUSES:
                return ev
        return None

    def create(self, signal: dict) -> tuple[dict, bool]:
        existing = self.open_event(signal["asset_id"], signal["event_type"])
        if existing:
            existing["suppressed"] += 1
            return existing, False
        ev = {
            "event_id": f"LAB-EVT-{signal['asset_id']}-{uuid.uuid4().hex[:6]}",
            "asset_id": signal["asset_id"],
            "event_type": signal["event_type"],
            "window_start": signal["window_start"],
            "window_end": signal["window_end"],
            "status": "DETECTED",
            "suppressed": 0,
        }
        self.events.append(ev)
        return ev, True

    def set_status(self, event_id: str, status: str) -> None:
        for ev in self.events:
            if ev["event_id"] == event_id:
                ev["status"] = status


# ---- 3. 고정 시험 구간 -----------------------------------------------------------
def fixed_test_ids() -> list[int]:
    """평가에 쓰는 시험 사이클 번호. 호출할 때마다 같아야 한다."""
    return list(E.fixed_split()[2])


# ---- 4. 지속 조건 비교 -----------------------------------------------------------
def compare_sustain(values=(1, 5, 10, 20), k_sigma: float = 4.0, min_delta_c: float = 3.0, smooth_s: int = 5) -> list[dict]:
    """같은 시험 구간에서 sustain_s 만 바꿔 평가한다. 다른 매개변수는 고정한다."""
    out = []
    for s in values:
        r = E.evaluate(k_sigma=k_sigma, min_delta_c=min_delta_c, sustain_s=s, smooth_s=smooth_s)
        out.append(
            {
                "sustain_s": s,
                "tp": r["tp"],
                "fp": r["fp"],
                "fn": r["fn"],
                "tn": r["tn"],
                "false_alarm_rate": r["false_alarm_rate"],
                "miss_rate": r["miss_rate"],
                "mean_delay_s": r["mean_delay_s"],
                "fp_cycles": [x["cycle"] for x in r["rows"] if x["pred"] and x["cooler_pct"] == 100],
            }
        )
    return out


# ---- 제공: 시뮬레이터 스트림 (DB 에 쓰지 않는다) --------------------------------
def simulate_rows(seconds: int = 180, cooling_eff: float = 1.0, seed: int = 7, degrade_at: int = 0, spike_at: int | None = None, dropout_at: int | None = None, dropout_s: int = 3) -> list[dict]:
    """HYD-01 시뮬레이터 → 품질 검사까지 거친 관측 목록. degrade_at 초에 냉각 성능을 cooling_eff 로 바꾼다."""
    sim = HydraulicSimulator("HYD-01", seed=seed)
    checker = SensorQualityChecker()
    rows = []
    for t in range(seconds):
        if t == degrade_at:
            sim.inject_cooling_degradation(cooling_eff)
        if spike_at is not None and t == spike_at:
            sim.inject_sensor_fault("spike", 7)  # 7초 주입 중 첫 1초만 +30°C 급등
        if dropout_at is not None and t == dropout_at:
            sim.inject_sensor_fault("dropout", dropout_s)
        rows.extend(checker.check_many(sim.step()))
    return rows


def run_stream(rows: list[dict], detector: SustainDetector, book: EventBook) -> dict:
    signals = created = 0
    for r in rows:
        for sig in detector.feed(r):
            signals += 1
            _, new = book.create(sig)
            created += int(new)
    return {"signals": signals, "events_created": created, "suppressed": signals - created}
