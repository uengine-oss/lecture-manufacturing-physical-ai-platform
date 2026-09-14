"""설비 런타임: B1 시뮬레이터 → B2 품질 검사 → B3 저장 → B5 탐지 를 1초 단위로 돌린다.

대시보드 서버는 백그라운드 루프로, 테스트와 시나리오 스크립트는 동기 호출로 같은 코드를 쓴다.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b2_quality.checks import SensorQualityChecker
from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b5_detect.detector import ThresholdDetector
from hydops.config import TH


class PlantRuntime:
    def __init__(self, assets=("HYD-01",), seed: int = 42, scenario: str = "live", run_id: str | None = None, start: datetime | None = None):
        start = start or datetime.now(timezone.utc).replace(microsecond=0)
        self.run_id = store.create_run("simulator", scenario, seed=seed, run_id=run_id, note="교육용 합성 데이터")
        self.sims = {a: HydraulicSimulator(a, seed=seed + i, start=start) for i, a in enumerate(assets)}
        self.checker = SensorQualityChecker()
        self.detector = ThresholdDetector(TH)
        self.lock = threading.RLock()
        self.listeners = []  # 새 사건 콜백 (Watch 브리지·오케스트레이터)

    def now(self, asset_id: str = "HYD-01") -> datetime:
        return self.sims[asset_id].state.t

    def tick(self, seconds: int = 1) -> list[dict]:
        new_events = []
        with self.lock:
            for _ in range(seconds):
                rows = []
                for sim in self.sims.values():
                    rows.extend(sim.step())
                checked = self.checker.check_many(rows)
                store.insert_observations(self.run_id, checked)
                new_events.extend(self._detect(checked))
        self._notify(new_events)
        return new_events

    def _detect(self, checked: list[dict]) -> list[dict]:
        created_events = []
        for r in checked:
            for sig in self.detector.feed(r):
                ev, created = store.create_event(
                    self.run_id, sig.asset_id, sig.event_type, sig.window_start, sig.window_end,
                    TH.rule_version if sig.event_type == "COOLING_ANOMALY" else sig.evidence["rule"], sig.evidence,
                )
                if created:
                    graph.upsert_event_ref(ev["event_id"], ev["asset_id"], ev["event_type"], ev["status"])
                    created_events.append(ev)
        return created_events

    def _notify(self, events: list[dict]) -> None:
        for ev in events:
            for fn in self.listeners:
                fn(ev)

    def detect(self, checked: list[dict]) -> list[dict]:
        """외부에서 적재한 품질 검사 관측을 같은 탐지기에 넣는다."""
        with self.lock:
            events = self._detect(checked)
        self._notify(events)
        return events
