"""S06 제공 코드 (수정하지 않는다) — DB·서버 없이 실제 에이전트·조치 코드를 돌리는 메모리 사본.

- 시뮬레이터(B1)·품질 검사(B2)·요약(recent_summary)·제안 검사(executor.propose_action)·실행/재측정(service)은 실제 코드를 쓴다.
- PostgreSQL(store) 과 Neo4j(graph) 만 메모리 사본으로 바꿔 끼운다. 사본은 SOP 마크다운과 graph.ACTIONS 에서 만든다.
- 공유 DB 에 아무것도 쓰지 않는다 (run_id 는 LAB-S06).
"""
from __future__ import annotations

import itertools
from datetime import timedelta
from types import SimpleNamespace

from hydops.b1_data.simulator import HydraulicSimulator
from hydops.b2_quality.checks import SensorQualityChecker
from hydops.b4_ontology import graph
from hydops.b5_detect.detector import recent_summary

DOCS = graph.load_sop_docs()
ACTIONS = {a["action_id"]: a for a in graph.ACTIONS}
ACTION_KEYS = ("action_id", "name", "min_value", "max_value", "default_value", "requires_approval")
RUN_ID = "LAB-S06"


# ---- 그래프 사본 (graph.applicable_sops / asset_context 와 같은 모양) ------------------------
def applicable_sops(asset_id: str, event_type: str = "COOLING_ANOMALY") -> list[dict]:
    rows = []
    for d in sorted(DOCS, key=lambda d: d["doc_id"]):
        if d["status"] == "active" and d["event_type"] == event_type and asset_id in d["applies_to"]:
            rows.append({
                "doc_id": d["doc_id"], "version": d["version"], "title": d["title"], "effective_date": d["effective_date"],
                "approver_role": d["approver_role"],
                "allowed_actions": [{k: ACTIONS[x].get(k) for k in ACTION_KEYS} for x in d["allows"]],
            })
    return rows


def asset_context(asset_id: str) -> dict:
    sops = applicable_sops(asset_id, "COOLING_ANOMALY") + applicable_sops(asset_id, "SENSOR_FAULT")
    allowed = {}
    for s in sops:
        for a in s["allowed_actions"]:
            allowed[a["action_id"]] = a
    return {
        "asset_id": asset_id, "found": True,
        "sensors": [{"sensor_id": f"{asset_id}.{s['code']}", "code": s["code"], "unit": s["unit"]} for s in graph.SENSORS],
        "applicable_sops": [{k: s[k] for k in ("doc_id", "version", "title", "effective_date", "approver_role")} for s in sops],
        "allowed_actions": list(allowed.values()),
    }


def search_sop(asset_id: str, event_type: str, query: str | None = None, k: int = 5) -> dict:
    """검색 사본: 적용 SOP(active·설비·사건 유형)의 절을 문서 순서로 돌려준다. 벡터 순위는 흉내 내지 않는다."""
    keys = {(s["doc_id"], s["version"]) for s in applicable_sops(asset_id, event_type)}
    hits = []
    for d in sorted(DOCS, key=lambda d: d["doc_id"]):
        if (d["doc_id"], d["version"]) in keys:
            for s in d["sections"]:
                hits.append({"doc_id": d["doc_id"], "version": d["version"], "section": s["section_no"], "heading": s["heading"], "score": None, "text": s["text"]})
    return {"asset_id": asset_id, "event_type": event_type, "query": query, "hits": hits[:k]}


# ---- PostgreSQL 사본 (store 함수 중 service·executor 가 쓰는 것만) ---------------------------
class MemoryStore:
    def __init__(self):
        self.events, self.history, self.approvals, self.actions, self.verifications, self.obs = {}, [], [], [], [], []
        self._seq = itertools.count(1)

    def _id(self, prefix):
        return f"{prefix}-LAB{next(self._seq):04d}"

    def add_event(self, asset_id, event_type, ts, status="DETECTED"):
        eid = f"EVT-LAB-{asset_id}-{next(self._seq):03d}"
        self.events[eid] = {"event_id": eid, "run_id": RUN_ID, "asset_id": asset_id, "event_type": event_type, "window_start": ts,
                            "window_end": ts, "rule_version": "lab", "evidence": {}, "status": status, "status_reason": None, "proposal": None}
        self.history.append((eid, None, status, "detector"))
        return dict(self.events[eid])

    def get_event(self, event_id):
        ev = self.events.get(event_id)
        return dict(ev) if ev else None

    def transition(self, event_id, to_status, actor, detail=None, reason=None, **fields):
        ev = self.events[event_id]
        self.history.append((event_id, ev["status"], to_status, actor))
        ev["status"] = to_status
        if reason is not None:
            ev["status_reason"] = reason
        ev.update(fields)
        return dict(ev)

    def record_approval(self, event_id, approver, decision, action_id, approved_value, comment=None):
        apr = {"approval_id": self._id("APR"), "event_id": event_id, "approver": approver, "decision": decision,
               "action_id": action_id, "approved_value": approved_value, "comment": comment}
        self.approvals.append(apr)
        return dict(apr)

    def get_approval(self, approval_id):
        return next((dict(a) for a in self.approvals if a["approval_id"] == approval_id), None)

    def approvals_for(self, event_id):
        return [dict(a) for a in self.approvals if a["event_id"] == event_id]

    def find_action_log(self, idem_key):
        return next((dict(a) for a in self.actions if a["idempotency_key"] == idem_key), None)

    def insert_action_log(self, event_id, approval_id, action_id, value, idem_key, status, detail, sim_ts=None):
        old = self.find_action_log(idem_key)
        if old:
            return old, False
        row = {"action_log_id": self._id("ACT"), "event_id": event_id, "approval_id": approval_id, "action_id": action_id,
               "requested_value": value, "idempotency_key": idem_key, "command_status": status, "command_detail": detail, "sim_ts": sim_ts}
        self.actions.append(row)
        return dict(row), True

    def get_action_log(self, action_log_id):
        return next((dict(a) for a in self.actions if a["action_log_id"] == action_log_id), None)

    def actions_for(self, event_id):
        return [dict(a) for a in self.actions if a["event_id"] == event_id]

    def observations_between(self, asset_id, sensor_id, start, end, run_id=None):
        return [r for r in self.obs if r["asset_id"] == asset_id and r["sensor_id"] == sensor_id and start < r["ts"] <= end]

    def insert_verification(self, action_log_id, event_id, start, end, outcome, metrics):
        row = {"verification_id": self._id("VER"), "action_log_id": action_log_id, "event_id": event_id,
               "window_start": start, "window_end": end, "outcome": outcome, "metrics": metrics}
        self.verifications.append(row)
        return dict(row)

    def recent_rows(self, asset_id, seconds=60):
        rows = [r for r in self.obs if r["asset_id"] == asset_id]
        if not rows:
            return []
        until = rows[-1]["ts"]
        return [r for r in rows if r["ts"] > until - timedelta(seconds=seconds)]


class LabPlant:
    """시뮬레이터 여러 대 + 품질 검사 + 메모리 저장소."""

    def __init__(self, assets=("HYD-01", "HYD-02", "HYD-03"), seed=42):
        self.store = MemoryStore()
        self.sims = {a: HydraulicSimulator(a, seed=seed + i) for i, a in enumerate(assets)}
        self.checker = SensorQualityChecker()

    def tick(self, seconds=1):
        for _ in range(seconds):
            rows = []
            for sim in self.sims.values():
                rows.extend(sim.step())
            self.store.obs.extend(self.checker.check_many(rows))

    def recent_window(self, asset_id, seconds=60, until=None, run_id=None):
        return {"asset_id": asset_id, "seconds": seconds, "sensors": recent_summary(self.store.recent_rows(asset_id, seconds))}


def patch_system(monkeypatch, plant: LabPlant):
    """실제 hydops 모듈의 store/graph 참조를 메모리 사본으로 바꾼다 (pytest monkeypatch — 테스트가 끝나면 원래대로)."""
    from hydops.b7_agent import agent
    from hydops.b7_agent import tools as T
    from hydops.b8_action import executor, service

    fake_graph = SimpleNamespace(applicable_sops=applicable_sops, asset_context=asset_context, upsert_event_ref=lambda *a, **k: None)
    monkeypatch.setattr(agent, "store", plant.store)
    monkeypatch.setattr(T, "store", plant.store)
    monkeypatch.setattr(service, "store", plant.store)
    monkeypatch.setattr(executor, "store", plant.store)
    monkeypatch.setattr(service, "kg", fake_graph)
    monkeypatch.setattr(executor, "graph", fake_graph)
    monkeypatch.setattr(T, "get_asset_context_impl", asset_context)
    monkeypatch.setattr(T, "get_recent_window_impl", plant.recent_window)
    monkeypatch.setattr(T, "search_sop_impl", lambda asset_id, event_type, query=None: search_sop(asset_id, event_type, query))


def make_tools(plant: LabPlant, trace: list) -> dict:
    """학생 에이전트에 넘길 도구 4종 (이름 → 함수). 호출할 때마다 trace 에 기록한다. 실행 도구는 없다."""
    from hydops.b8_action import executor

    def wrap(name, fn):
        def call(**kwargs):
            result = fn(**kwargs)
            trace.append({"tool": name, "args": kwargs, "result": result})
            return result
        return call

    return {
        "get_asset_context": wrap("get_asset_context", lambda asset_id: asset_context(asset_id)),
        "get_recent_window": wrap("get_recent_window", lambda asset_id, seconds=60: plant.recent_window(asset_id, seconds)),
        "search_sop": wrap("search_sop", lambda asset_id, event_type, query=None: search_sop(asset_id, event_type, query)),
        "propose_action": wrap("propose_action", lambda event_id, action_id, value, citations: executor.propose_action(event_id, action_id, value, citations)),
    }
