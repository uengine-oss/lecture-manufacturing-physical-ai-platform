"""B1 · 상태를 가진 유압설비 시뮬레이터 (폐루프 검증용, 합성 데이터).

원본 CSV 재생은 조치에 반응하지 않으므로 온도·부하·냉각 상태를 가진 별도 모델을 쓴다.
모델은 교육용 가정이며 실제 물리 인과관계를 입증하지 않는다.

    T_ss = T_ambient + k * load^2 / cooling_eff
    dT/dt = (T_ss - T) / tau

- 정상(cooling 1.0, load 1.0): 약 45°C
- 냉각 성능 저하(cooling 0.4): 부하 1.0 → 약 67.5°C (경보), 부하 0.8 → 약 54°C (회복)
- 심각한 저하(cooling 0.25): 부하 0.8 에서도 약 68°C (미개선 → 이관)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

T_AMBIENT = 30.0
K_HEAT = 15.0
TAU_S = 12.0


@dataclass
class SimState:
    asset_id: str
    t: datetime
    temp_c: float
    load: float = 1.0
    cooling_eff: float = 1.0
    step_no: int = 0
    # 센서 고장 주입 상태 (설비 상태와 별개)
    sensor_fault: str | None = None  # dropout / stuck / spike
    sensor_fault_left: int = 0
    stuck_value: float | None = None
    command_fail_next: bool = False  # 도구 실패 분기 실습용
    events: list = field(default_factory=list)


class HydraulicSimulator:
    def __init__(self, asset_id: str = "HYD-01", seed: int = 42, start: datetime | None = None, temp_c: float | None = None):
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        start = start or datetime(2027, 1, 28, 14, 0, tzinfo=timezone.utc)
        t0 = temp_c if temp_c is not None else self.steady_temp(1.0, 1.0)
        self.state = SimState(asset_id=asset_id, t=start, temp_c=t0)

    @staticmethod
    def steady_temp(load: float, cooling_eff: float) -> float:
        return T_AMBIENT + K_HEAT * load**2 / max(cooling_eff, 1e-3)

    # ---- 시나리오 주입 -------------------------------------------------
    def inject_cooling_degradation(self, cooling_eff: float = 0.4) -> None:
        self.state.cooling_eff = cooling_eff
        self.state.events.append({"t": self.state.t.isoformat(), "type": "inject_cooling", "cooling_eff": cooling_eff})

    def inject_sensor_fault(self, kind: str = "dropout", seconds: int = 20) -> None:
        self.state.sensor_fault = kind
        self.state.sensor_fault_left = seconds
        self.state.stuck_value = None
        self.state.events.append({"t": self.state.t.isoformat(), "type": f"inject_sensor_{kind}", "seconds": seconds})

    def fail_next_command(self) -> None:
        self.state.command_fail_next = True

    # ---- 조치 -----------------------------------------------------------
    def apply_load(self, load: float) -> dict:
        """시뮬레이터 명령. 명령 성공은 설비 회복을 뜻하지 않는다."""
        if self.state.command_fail_next:
            self.state.command_fail_next = False
            return {"ok": False, "error": "actuator_timeout", "sim_ts": self.state.t.isoformat()}
        prev = self.state.load
        self.state.load = load
        self.state.events.append({"t": self.state.t.isoformat(), "type": "set_load", "from": prev, "to": load})
        return {"ok": True, "from": prev, "to": load, "sim_ts": self.state.t.isoformat()}

    def apply_fan_boost(self, factor: float) -> dict:
        """HYD-02 공랭식 팬 증속 (교육용 가정: 냉각 효율 × 팬 배수², 최대 1.0)."""
        if self.state.command_fail_next:
            self.state.command_fail_next = False
            return {"ok": False, "error": "actuator_timeout", "sim_ts": self.state.t.isoformat()}
        prev = self.state.cooling_eff
        self.state.cooling_eff = min(1.0, prev * factor**2)
        self.state.events.append({"t": self.state.t.isoformat(), "type": "fan_boost", "from": prev, "to": self.state.cooling_eff})
        return {"ok": True, "cooling_from": round(prev, 3), "cooling_to": round(self.state.cooling_eff, 3), "sim_ts": self.state.t.isoformat()}

    # ---- 1초 진행 --------------------------------------------------------
    def step(self) -> list[dict]:
        s = self.state
        target = self.steady_temp(s.load, s.cooling_eff)
        s.temp_c += (target - s.temp_c) * (1 - math.exp(-1.0 / TAU_S))
        s.t += timedelta(seconds=1)
        s.step_no += 1

        temp_obs: float | None = s.temp_c + float(self.rng.normal(0, 0.25))
        if s.sensor_fault and s.sensor_fault_left > 0:
            if s.sensor_fault == "dropout":
                temp_obs = None
            elif s.sensor_fault == "stuck":
                s.stuck_value = s.stuck_value if s.stuck_value is not None else round(temp_obs, 2)
                temp_obs = s.stuck_value
            elif s.sensor_fault == "spike":
                temp_obs = temp_obs + 30.0 if s.sensor_fault_left % 7 == 0 else temp_obs
            s.sensor_fault_left -= 1
            if s.sensor_fault_left == 0:
                s.sensor_fault = None

        pressure = 150.0 * s.load + float(self.rng.normal(0, 1.5))
        flow = 9.0 * s.load + float(self.rng.normal(0, 0.08))
        base = {"asset_id": s.asset_id, "ts": s.t, "elapsed_s": s.step_no, "origin_cycle_id": None, "is_synthetic": True}
        return [
            {**base, "sensor_id": "TS1", "raw_value": None if temp_obs is None else round(temp_obs, 3), "unit": "°C", "agg": None},
            {**base, "sensor_id": "PS1", "raw_value": round(pressure, 3), "unit": "bar", "agg": None},
            {**base, "sensor_id": "FS1", "raw_value": round(flow, 4), "unit": "L/min", "agg": None},
        ]

    def run(self, seconds: int) -> list[dict]:
        rows: list[dict] = []
        for _ in range(seconds):
            rows.extend(self.step())
        return rows

    def snapshot(self) -> dict:
        d = asdict(self.state)
        d["t"] = self.state.t.isoformat()
        d["steady_temp_c"] = round(self.steady_temp(self.state.load, self.state.cooling_eff), 2)
        d.pop("events")
        return d
