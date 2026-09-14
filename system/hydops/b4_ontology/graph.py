"""B4 · Neo4j 설비 관계와 업무 개념.

시계열 전체를 그래프 노드로 만들지 않는다. 설비·센서·SOP·조치와 사건 참조만 둔다.
수치 상세는 PostgreSQL 에서 asset_id 로 조회한다.

Ontologic 대응: Resource=유압설비·냉각기, Measure=온도·유량·압력, Driver=부하·냉각 성능,
Process=운전·점검, KPI=이상 지속 시간·불필요 조치 건수. Asset 은 Resource 의 수업용 구체 클래스다.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml
from neo4j import Driver, GraphDatabase

from hydops.config import SETTINGS

_driver: Driver | None = None


def driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(SETTINGS.neo4j_uri, auth=(SETTINGS.neo4j_user, SETTINGS.neo4j_password))
    return _driver


@contextmanager
def session() -> Iterator[Any]:
    with driver().session() as s:
        yield s


def run(cypher: str, **params) -> list[dict]:
    with session() as s:
        return [r.data() for r in s.run(cypher, **params)]


CONSTRAINTS = [
    "CREATE CONSTRAINT asset_id IF NOT EXISTS FOR (n:Asset) REQUIRE n.asset_id IS UNIQUE",
    "CREATE CONSTRAINT sensor_id IF NOT EXISTS FOR (n:Sensor) REQUIRE n.sensor_id IS UNIQUE",
    "CREATE CONSTRAINT sop_key IF NOT EXISTS FOR (n:SOP) REQUIRE n.sop_key IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (n:SOPSection) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.action_id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (n:Event) REQUIRE n.event_id IS UNIQUE",
]

# 교육용 설비 목록 (강사 작성)
ASSETS = [
    {"asset_id": "HYD-01", "name": "유압설비 1호기", "cooling": "수랭식 냉각기", "line": "L1", "educational": True},
    {"asset_id": "HYD-02", "name": "유압설비 2호기", "cooling": "공랭식 팬", "line": "L2", "educational": True},
    # 신규 설비: SOP 가 아직 등록되지 않았다 → 근거 없음 보류 사례
    {"asset_id": "HYD-03", "name": "유압설비 3호기(신규)", "cooling": "수랭식 냉각기", "line": "L3", "educational": True},
]
SENSORS = [
    {"code": "TS1", "quantity": "temperature", "unit": "°C", "hz": 1, "name": "탱크 온도"},
    {"code": "PS1", "quantity": "pressure", "unit": "bar", "hz": 100, "name": "주 압력"},
    {"code": "FS1", "quantity": "flow", "unit": "L/min", "hz": 10, "name": "주 유량"},
]
ACTIONS = [
    {"action_id": "REDUCE_LOAD", "name": "승인 부하 감소", "kind": "equipment", "min_value": 0.6, "max_value": 1.0, "default_value": 0.8, "requires_approval": True},
    {"action_id": "SENSOR_CHECK", "name": "센서 점검 요청", "kind": "inspection", "requires_approval": False},
    {"action_id": "ESCALATE", "name": "정비 책임자 이관", "kind": "handover", "requires_approval": False},
    {"action_id": "FAN_BOOST", "name": "냉각 팬 증속", "kind": "equipment", "min_value": 1.0, "max_value": 1.5, "default_value": 1.3, "requires_approval": True},
]


def load_sop_docs(doc_dir: Path | None = None) -> list[dict]:
    """SOP 마크다운(frontmatter + '## n. 제목' 절)을 읽는다."""
    doc_dir = doc_dir or Path(__file__).resolve().parent.parent / "b6_sop" / "docs"
    docs = []
    for p in sorted(doc_dir.glob("*.md")):
        text = p.read_text()
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm)
        sections = []
        current = None
        for line in body.strip().splitlines():
            if line.startswith("## "):
                num, _, heading = line[3:].partition(". ")
                current = {"section_no": num.strip(), "heading": heading.strip(), "lines": []}
                sections.append(current)
            elif current is not None and line.strip():
                current["lines"].append(line.strip())
        for s in sections:
            s["text"] = " ".join(s.pop("lines"))
        meta["sop_key"] = f"{meta['doc_id']}@v{meta['version']}"
        meta["effective_date"] = str(meta["effective_date"])
        meta["sections"] = sections
        meta["path"] = p.name
        docs.append(meta)
    return docs


def reset_graph() -> None:
    run("MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['Asset','Sensor','SOP','SOPSection','Action','Event','Resource','Measure','Driver','Process','KPI','Component']) DETACH DELETE n")


def seed_graph(docs: list[dict] | None = None) -> dict:
    """제공 MERGE 문으로 초기 그래프를 적재한다. 여러 번 실행해도 결과가 같다(MERGE)."""
    for c in CONSTRAINTS:
        run(c)
    docs = docs or load_sop_docs()

    for a in ASSETS:
        run(
            """MERGE (a:Asset {asset_id:$asset_id})
               SET a:Resource, a.name=$name, a.cooling=$cooling, a.line=$line, a.educational=$educational
               MERGE (c:Component:Resource {component_id:$asset_id + '.COOLER'})
               SET c.name=$cooling
               MERGE (a)-[:HAS_COMPONENT]->(c)""",
            **a,
        )
        for s in SENSORS:
            run(
                """MATCH (a:Asset {asset_id:$asset_id})
                   MERGE (s:Sensor {sensor_id:$asset_id + '.' + $code})
                   SET s:Measure, s.code=$code, s.quantity=$quantity, s.unit=$unit, s.hz=$hz, s.name=$name
                   MERGE (a)-[:HAS_SENSOR]->(s)""",
                asset_id=a["asset_id"],
                **s,
            )

    for act in ACTIONS:
        run("MERGE (x:Action {action_id:$action_id}) SET x += $props", action_id=act["action_id"], props=act)

    # Driver / Process / KPI (Ontologic 관점)
    run(
        """MERGE (load:Driver {driver_id:'LOAD'}) SET load.name='운전 부하'
           MERGE (cool:Driver {driver_id:'COOLING_PERF'}) SET cool.name='냉각 성능'
           MERGE (op:Process {process_id:'OPERATION'}) SET op.name='운전'
           MERGE (insp:Process {process_id:'INSPECTION'}) SET insp.name='점검'
           MERGE (k1:KPI {kpi_id:'ANOMALY_DURATION_S'}) SET k1.name='이상 지속 시간'
           MERGE (k2:KPI {kpi_id:'UNNEEDED_ACTIONS'}) SET k2.name='불필요 조치 건수'"""
    )
    # '냉각 성능이 온도에 영향을 준다' — 관계에는 근거 종류를 표시한다. 그렸다고 실측 인과가 되지 않는다.
    # 근거 문서는 그 설비에 적용되는 SOP 여야 한다. 적용 SOP 가 없는 설비는 시뮬레이터 가정으로만 표시한다.
    basis_by_asset = {
        "HYD-01": ("document", "SOP-COOL-001@v2 §3"),
        "HYD-02": ("document", "SOP-COOL-002@v1 §2"),
    }
    run("MATCH (:Driver)-[r:AFFECTS]->(:Sensor) DELETE r")
    for a in ASSETS:
        basis, source = basis_by_asset.get(a["asset_id"], ("simulator_assumption", "simulator.py T_ss 식 (적용 SOP 없음)"))
        run(
            """MATCH (cool:Driver {driver_id:'COOLING_PERF'}), (load:Driver {driver_id:'LOAD'})
               MATCH (:Asset {asset_id:$asset_id})-[:HAS_SENSOR]->(s:Sensor {code:'TS1'})
               MERGE (cool)-[r1:AFFECTS]->(s) SET r1.basis=$basis, r1.source=$source, r1.verified_causal=false
               MERGE (load)-[r2:AFFECTS]->(s) SET r2.basis='simulator_assumption', r2.source='simulator.py T_ss 식', r2.verified_causal=false""",
            asset_id=a["asset_id"], basis=basis, source=source,
        )
    run(
        """MATCH (a:Asset) MATCH (op:Process {process_id:'OPERATION'}), (insp:Process {process_id:'INSPECTION'})
           MERGE (op)-[:RUNS_ON]->(a) MERGE (insp)-[:RUNS_ON]->(a)
           WITH a MATCH (k:KPI) MERGE (k)-[:MEASURED_FOR]->(a)"""
    )

    for d in docs:
        run(
            """MERGE (s:SOP {sop_key:$sop_key})
               SET s.doc_id=$doc_id, s.title=$title, s.version=$version, s.effective_date=date($effective_date),
                   s.status=$status, s.event_type=$event_type, s.approver_role=$approver_role, s.educational=$educational""",
            **{k: d[k] for k in ("sop_key", "doc_id", "title", "version", "effective_date", "status", "event_type", "approver_role", "educational")},
        )
        for asset_id in d["applies_to"]:
            run("MATCH (s:SOP {sop_key:$k}), (a:Asset {asset_id:$a}) MERGE (s)-[:APPLIES_TO]->(a)", k=d["sop_key"], a=asset_id)
        for action_id in d["allows"]:
            run("MATCH (s:SOP {sop_key:$k}), (x:Action {action_id:$x}) MERGE (s)-[:ALLOWS]->(x)", k=d["sop_key"], x=action_id)
        for sec in d["sections"]:
            run(
                """MATCH (s:SOP {sop_key:$k})
                   MERGE (x:SOPSection {id:$id})
                   SET x.doc_id=$doc_id, x.version=$version, x.section_no=$no, x.heading=$heading, x.text=$text,
                       x.status=$status, x.asset_scope=$scope, x.event_type=$event_type
                   MERGE (s)-[:HAS_SECTION]->(x)""",
                k=d["sop_key"],
                id=f"{d['sop_key']}#{sec['section_no']}",
                doc_id=d["doc_id"],
                version=d["version"],
                no=sec["section_no"],
                heading=sec["heading"],
                text=f"[{d['doc_id']} v{d['version']} §{sec['section_no']} {sec['heading']}] {sec['text']}",
                status=d["status"],
                scope="|" + "|".join(d["applies_to"]) + "|",
                event_type=d["event_type"],
            )
    run(
        """MATCH (new:SOP), (old:SOP) WHERE new.doc_id = old.doc_id AND new.version = old.version + 1
           MERGE (new)-[:SUPERSEDES]->(old)"""
    )
    return graph_stats()


def graph_stats() -> dict:
    labels = ["Asset", "Component", "Sensor", "SOP", "SOPSection", "Action", "Event", "Driver", "Process", "KPI"]
    nodes = [{"label": l, "n": run(f"MATCH (n:`{l}`) RETURN count(n) AS n")[0]["n"]} for l in labels]
    rels = run("MATCH ()-[r]->() WHERE type(r) IN ['HAS_SENSOR','APPLIES_TO','HAS_SECTION','ALLOWS','SUPERSEDES','AFFECTS','ON_ASSET','CITES','HAS_COMPONENT','RUNS_ON','MEASURED_FOR'] RETURN type(r) AS rel, count(*) AS n")
    return {"nodes": {r["label"]: r["n"] for r in nodes}, "relationships": {r["rel"]: r["n"] for r in rels}}


# ---- 세 가지 매개변수 질의 (Golden Question 에 필요한 관계 탐색) -----------------
Q_ASSET_SENSORS = """
MATCH (a:Asset {asset_id:$asset_id})-[:HAS_SENSOR]->(s:Sensor)
RETURN s.sensor_id AS sensor_id, s.code AS code, s.quantity AS quantity, s.unit AS unit, s.hz AS hz
ORDER BY s.code
"""

Q_APPLICABLE_SOP = """
MATCH (sop:SOP)-[:APPLIES_TO]->(a:Asset {asset_id:$asset_id})
WHERE sop.status = 'active' AND sop.event_type = $event_type
OPTIONAL MATCH (sop)-[:ALLOWS]->(act:Action)
RETURN sop.doc_id AS doc_id, sop.version AS version, sop.title AS title,
       toString(sop.effective_date) AS effective_date, sop.approver_role AS approver_role,
       collect(DISTINCT act {.action_id, .name, .min_value, .max_value, .default_value, .requires_approval}) AS allowed_actions
ORDER BY doc_id
"""

Q_EVENT_EVIDENCE = """
MATCH (e:Event {event_id:$event_id})-[:ON_ASSET]->(a:Asset)
OPTIONAL MATCH (e)-[c:CITES]->(sec:SOPSection)<-[:HAS_SECTION]-(sop:SOP)
RETURN e.event_id AS event_id, a.asset_id AS asset_id, e.event_type AS event_type, e.status AS status,
       collect(DISTINCT {doc_id: sop.doc_id, version: sop.version, section: sec.section_no, heading: sec.heading}) AS citations
"""


def asset_sensors(asset_id: str) -> list[dict]:
    return run(Q_ASSET_SENSORS, asset_id=asset_id)


def applicable_sops(asset_id: str, event_type: str = "COOLING_ANOMALY") -> list[dict]:
    rows = run(Q_APPLICABLE_SOP, asset_id=asset_id, event_type=event_type)
    for r in rows:
        r["allowed_actions"] = [a for a in r["allowed_actions"] if a.get("action_id")]
    return rows


def asset_context(asset_id: str) -> dict:
    """get_asset_context 도구의 본체: 센서·적용 SOP·허용 조치."""
    asset = run("MATCH (a:Asset {asset_id:$asset_id}) RETURN a {.*} AS a", asset_id=asset_id)
    if not asset:
        return {"asset_id": asset_id, "found": False}
    sops = applicable_sops(asset_id, "COOLING_ANOMALY") + applicable_sops(asset_id, "SENSOR_FAULT")
    allowed = {}
    for s in sops:
        for a in s["allowed_actions"]:
            allowed[a["action_id"]] = a
    return {
        "asset_id": asset_id,
        "found": True,
        "asset": asset[0]["a"],
        "sensors": asset_sensors(asset_id),
        "applicable_sops": [{k: s[k] for k in ("doc_id", "version", "title", "effective_date", "approver_role")} for s in sops],
        "allowed_actions": list(allowed.values()),
    }


def upsert_event_ref(event_id: str, asset_id: str, event_type: str, status: str, citations: list[dict] | None = None) -> None:
    """사건은 Asset 과 연결한 참조 노드만 둔다 (수치 상세는 PostgreSQL)."""
    run(
        """MATCH (a:Asset {asset_id:$asset_id})
           MERGE (e:Event {event_id:$event_id}) SET e.event_type=$event_type, e.status=$status
           MERGE (e)-[:ON_ASSET]->(a)""",
        event_id=event_id,
        asset_id=asset_id,
        event_type=event_type,
        status=status,
    )
    for c in citations or []:
        run(
            """MATCH (e:Event {event_id:$event_id}), (sec:SOPSection {id:$sid}) MERGE (e)-[:CITES]->(sec)""",
            event_id=event_id,
            sid=f"{c['doc_id']}@v{c['version']}#{c['section']}",
        )


def event_evidence(event_id: str) -> dict | None:
    rows = run(Q_EVENT_EVIDENCE, event_id=event_id)
    return rows[0] if rows else None
