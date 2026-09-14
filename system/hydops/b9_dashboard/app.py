"""B9 · 사건 관제 API 서버 + 관제 화면.

- 시뮬레이터 루프: B1 → B2 → B3 → B5 를 SPEED 배속으로 돌린다
- ORCHESTRATION=local  : 새 사건을 로컬 LangGraph(B7·B8)가 처리한다 (1~5회차)
- ORCHESTRATION=platform: 사건 처리는 교육용 플랫폼 프로세스가 맡는다 (6~9회차). 여기서는 사건만 만든다
- /mcp/ : 도구 계약 6종 (MCP streamable HTTP)
- /api/system/* : 플랫폼 프로세스 전용 시스템 API (토큰 필요)
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b6_sop import search
from hydops.b8_action import service
from hydops.b8_action.workflow import Orchestrator
from hydops.golden import golden_questions
from hydops.mcp_tools import build_mcp
from hydops.runtime import PlantRuntime

STATIC = Path(__file__).parent / "static"
SYSTEM_TOKEN = os.environ.get("HYDOPS_SYSTEM_TOKEN", "lab-system-token")


class Plant:
    def __init__(self):
        self.mode = os.environ.get("ORCHESTRATION", "local")
        self.speed = float(os.environ.get("SPEED", "1"))
        self.paused = False
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.runtime: PlantRuntime | None = None
        self.orc: Orchestrator | None = None
        self.last_error = None
        self._stop = threading.Event()
        self.reset(seed=42)

    def reset(self, seed: int = 42, scenario: str = "live"):
        if self.orc:
            self.orc.close()
        self.runtime = PlantRuntime(assets=("HYD-01", "HYD-02", "HYD-03"), seed=seed, scenario=f"{scenario}-{self.mode}")
        store.end_open_events_of_other_runs(self.runtime.run_id)
        self.orc = Orchestrator(self.runtime) if self.mode == "local" else None
        if self.orc:
            self.runtime.listeners.append(lambda ev: self.pool.submit(self._start_case, ev["event_id"]))

    def _start_case(self, event_id: str):
        try:
            self.orc.start(event_id)
        except Exception as e:  # noqa: BLE001 — 관제 화면에 보여준다
            self.last_error = f"{event_id}: {e!r}"

    def loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            if not self.paused:
                try:
                    self.runtime.tick(1)
                    if self.orc:
                        self.orc.poll()
                except Exception as e:  # noqa: BLE001
                    self.last_error = repr(e)
            self._stop.wait(max(0.0, 1.0 / self.speed - (time.time() - t0)))


plant: Plant | None = None


def get_runtime():
    return plant.runtime


mcp = build_mcp(get_runtime)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global plant
    store.init_schema()
    if not graph.run("MATCH (s:SOPSection) WHERE s.embedding_openai IS NOT NULL OR s.embedding_offline IS NOT NULL RETURN count(s) AS n")[0]["n"]:
        graph.seed_graph()
        search.index_sections()
    plant = Plant()
    th = threading.Thread(target=plant.loop, daemon=True)
    th.start()
    async with mcp.session_manager.run():
        yield
    plant._stop.set()


app = FastAPI(title="HydOps 관제 API (B9)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _require_system(token: str | None):
    if token != SYSTEM_TOKEN:
        raise HTTPException(401, "system token required")


@app.get("/api/state")
def state():
    rt = plant.runtime
    return {
        "run_id": rt.run_id,
        "mode": plant.mode,
        "speed": plant.speed,
        "paused": plant.paused,
        "sim": {a: s.snapshot() for a, s in rt.sims.items()},
        "last_error": plant.last_error,
    }


@app.post("/api/control")
def control(body: dict = Body(...)):
    if "speed" in body:
        plant.speed = max(0.2, min(20.0, float(body["speed"])))
    if "paused" in body:
        plant.paused = bool(body["paused"])
    if body.get("reset"):
        plant.reset(seed=int(body.get("seed", 42)), scenario=body.get("scenario", "live"))
    return state()


@app.post("/api/sim/{asset_id}/inject")
def inject(asset_id: str, body: dict = Body(...)):
    sim = plant.runtime.sims[asset_id]
    kind = body["kind"]
    if kind == "cooling":
        sim.inject_cooling_degradation(float(body.get("cooling_eff", 0.4)))
    elif kind == "severe":
        sim.inject_cooling_degradation(float(body.get("cooling_eff", 0.25)))
    elif kind == "restore":
        sim.inject_cooling_degradation(1.0)
    elif kind in ("dropout", "stuck", "spike"):
        sim.inject_sensor_fault(kind, int(body.get("seconds", 20)))
    elif kind == "fail_command":
        sim.fail_next_command()
    else:
        raise HTTPException(400, f"unknown kind {kind}")
    return sim.snapshot()


@app.get("/api/assets")
def assets():
    return [graph.asset_context(a) for a in plant.runtime.sims]


@app.get("/api/series")
def series(asset_id: str = "HYD-01", seconds: int = 180):
    rows = store.recent_window(asset_id, seconds, run_id=plant.runtime.run_id)
    out: dict = {}
    for r in rows:
        out.setdefault(r["sensor_id"], []).append({"ts": r["ts"], "raw": r["raw_value"], "value": r["value"], "flag": r["quality_flag"]})
    actions = []
    with store.connect() as c:
        actions = c.execute(
            "SELECT a.sim_ts, a.action_id, a.requested_value, a.command_status, a.event_id FROM action_log a JOIN event e USING (event_id) WHERE e.run_id=%s AND e.asset_id=%s",
            (plant.runtime.run_id, asset_id),
        ).fetchall()
    return {"asset_id": asset_id, "series": out, "actions": actions}


@app.get("/api/events")
def events(limit: int = 30, all_runs: bool = False):
    return store.list_events(limit, run_id=None if all_runs else plant.runtime.run_id)


@app.get("/api/events/{event_id}")
def event_detail(event_id: str):
    tr = store.event_trace(event_id)
    if not tr["event"]:
        raise HTTPException(404, "event not found")
    ev = tr["event"]
    tr["workflow"] = plant.orc.snapshot(event_id) if plant.orc and ev["process_ref"] is None else None
    if tr["workflow"]:
        tr["workflow"].pop("values", None)
    tr["graph"] = graph.event_evidence(event_id)
    tr["golden"] = golden_questions(ev["asset_id"], event_id, run_id=ev["run_id"], until=ev["window_end"]) if ev["event_type"] != "PRODUCT_QUALITY" else None
    sections = []
    for c in ((ev.get("proposal") or {}).get("proposal") or {}).get("citations", []):
        rows = graph.run("MATCH (x:SOPSection {id:$id}) RETURN x.text AS text, x.heading AS heading", id=f"{c['doc_id']}@v{c['version']}#{c['section']}")
        sections.append({**c, **(rows[0] if rows else {"text": None})})
    tr["citation_texts"] = sections
    return tr


@app.post("/api/events/{event_id}/decision")
def decision(event_id: str, body: dict = Body(...)):
    """로컬 모드의 사람 승인 (모의 승인 버튼)."""
    if plant.mode != "local":
        raise HTTPException(409, "platform 모드에서는 교육용 플랫폼의 승인 태스크에서 결정한다")
    return plant.orc.decide(event_id, body.get("approver", "operator"), body["decision"], body.get("value"), body.get("comment"))


@app.get("/api/sop/{doc_id}")
def sop_doc(doc_id: str):
    return graph.run(
        "MATCH (s:SOP {doc_id:$d})-[:HAS_SECTION]->(x) RETURN s.version AS version, s.status AS status, x.section_no AS section, x.heading AS heading, x.text AS text ORDER BY s.version, toInteger(x.section_no)",
        d=doc_id,
    )


# ---- 새 센서 별칭 매핑 (9회차) ------------------------------------------------------
@app.put("/api/sensors/{sensor_id}/aliases")
def set_aliases(sensor_id: str, body: dict = Body(...)):
    clash = graph.run(
        """MATCH (a:Asset)-[:HAS_SENSOR]->(me:Sensor {sensor_id:$id}) MATCH (a)-[:HAS_SENSOR]->(other:Sensor)
           WHERE other <> me AND any(x IN $aliases WHERE x = other.code OR x IN coalesce(other.aliases, []))
           RETURN other.sensor_id AS sensor_id""",
        id=sensor_id, aliases=body["aliases"],
    )
    if clash:
        raise HTTPException(409, {"error": "다른 센서가 이미 쓰는 이름", "sensors": [c["sensor_id"] for c in clash]})
    rows = graph.run("MATCH (s:Sensor {sensor_id:$id}) SET s.aliases=$aliases RETURN s {.*} AS s", id=sensor_id, aliases=body["aliases"])
    if not rows:
        raise HTTPException(404, "sensor not found")
    return rows[0]["s"]


@app.post("/api/ingest/{asset_id}")
def ingest(asset_id: str, body: dict = Body(...)):
    """외부 게이트웨이의 센서 이름을 그래프의 별칭으로 표준 센서 코드에 매핑해 적재한다."""
    mapped, unknown = [], set()
    for r in body["rows"]:
        hit = graph.run(
            "MATCH (:Asset {asset_id:$a})-[:HAS_SENSOR]->(s:Sensor) WHERE s.code=$n OR $n IN coalesce(s.aliases, []) RETURN s.code AS code, s.unit AS unit",
            a=asset_id,
            n=r["sensor"],
        )
        if not hit:
            unknown.add(r["sensor"])
            continue
        mapped.append({"asset_id": asset_id, "sensor_id": hit[0]["code"], "ts": datetime.fromisoformat(r["ts"]), "elapsed_s": None, "origin_cycle_id": None, "raw_value": r["value"], "unit": hit[0]["unit"], "agg": None, "is_synthetic": True})
    if unknown:
        raise HTTPException(422, {"error": "등록되지 않은 센서 별칭", "unknown": sorted(unknown)})
    checked = plant.runtime.checker.check_many(mapped)
    store.insert_observations(plant.runtime.run_id, checked)
    events = plant.runtime.detect(checked)  # 적재한 관측도 시뮬레이터 관측과 같은 탐지 경로를 지난다
    return {"inserted": len(checked), "flags": [c["quality_flag"] for c in checked], "events": [e["event_id"] for e in events]}


# ---- 플랫폼 프로세스 전용 시스템 API ---------------------------------------------------
@app.get("/api/system/events/pending")
def pending_events(x_lab_system_token: str | None = Header(None)):
    _require_system(x_lab_system_token)
    with store.connect() as c:
        return c.execute("SELECT event_id, asset_id, run_id, event_type, created_at FROM event WHERE status='DETECTED' AND process_ref IS NULL ORDER BY created_at LIMIT 1").fetchall()


@app.post("/api/system/events/{event_id}/process-ref")
def bind_process(event_id: str, body: dict = Body(...), x_lab_system_token: str | None = Header(None)):
    """event_id 와 실행 회차를 프로세스 인스턴스에 대응시킨다. 이미 대응이 있으면 기존 값을 돌려준다."""
    _require_system(x_lab_system_token)
    with store.connect() as c:
        row = c.execute(
            "UPDATE event SET process_ref=%s, updated_at=now() WHERE event_id=%s AND process_ref IS NULL RETURNING process_ref",
            (store._json(body), event_id),
        ).fetchone()
        if row:
            store.transition(event_id, store.get_event(event_id)["status"], "platform", {"process_ref": body})
            return {"bound": True, "process_ref": row["process_ref"]}
        return {"bound": False, "process_ref": store.get_event(event_id)["process_ref"]}


@app.post("/api/system/events/{event_id}/evidence")
def platform_evidence(event_id: str, body: dict = Body(...), x_lab_system_token: str | None = Header(None)):
    _require_system(x_lab_system_token)
    from hydops.b7_agent.agent import Proposal, verify_citations

    raw = Proposal(**body["proposal"])
    final, problems = verify_citations(raw, body.get("tool_trace_full", []))
    result = {"event_id": event_id, "mode": "platform", "model": body.get("model", "platform-agent"), "proposal": final.model_dump(), "raw_proposal": raw.model_dump(), "citation_problems": problems, "tool_trace": body.get("tool_trace", [])}
    try:
        service.gather_evidence(event_id, proposal_result=result)
    except service.EvidenceRefused as e:
        raise HTTPException(409, {"error": "EVENT_NOT_DETECTED", "status": e.status}) from e
    return {"status": store.get_event(event_id)["status"], "proposal": final.model_dump(), "citation_problems": problems}


@app.post("/api/system/events/{event_id}/decision")
def platform_decision(event_id: str, body: dict = Body(...), x_lab_system_token: str | None = Header(None)):
    _require_system(x_lab_system_token)
    return service.record_decision(event_id, body["approver"], body["decision"], body.get("value"), body.get("comment"))


app.mount("/mcp", mcp.streamable_http_app())
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
