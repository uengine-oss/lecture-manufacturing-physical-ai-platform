"""통합반 3회 · Neo4j 로 설비와 매뉴얼 연결 — 빈칸(____)을 채우는 실습 파일.

흐름: 적재 문장(MERGE)의 ID 확인 → 세 가지 Cypher 질의 → 그래프 결과에 최근 센서 값 붙이기

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python ../labs/integrated/S03/graph_lab.py
- 빈칸은 [빈칸 1]~[빈칸 5] 다섯 곳이다. 나머지 코드는 제공 코드이므로 고치지 않는다.
- 질의는 읽기 전용 세션으로 실행한다. MERGE 는 강사 시드와 같은 값일 때만 반영하고,
  새 노드·관계가 하나라도 생기면(= ID 가 틀림) 되돌린다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from neo4j import READ_ACCESS, WRITE_ACCESS

from hydops.b1_data import uci
from hydops.b3_tsdb import store
from hydops.b4_ontology import graph

____ = None  # 빈칸 표시
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 없는 관계 이름 경고는 결과(빈 목록)로 확인한다

# ---------------------------------------------------------------------------
# [빈칸 1] 적재 문장의 ID — 센서 ID 는 '설비ID.센서코드' (예: HYD-01 의 TS1)
# ---------------------------------------------------------------------------
MERGE_SENSOR = """
MATCH (a:Asset {asset_id:$asset_id})
MERGE (s:Sensor {sensor_id: $asset_id + ____ + $code})
SET s:Measure, s.code=$code, s.quantity=$quantity, s.unit=$unit, s.hz=$hz, s.name=$name
MERGE (a)-[:HAS_SENSOR]->(s)
RETURN s.sensor_id AS merged
"""

# SOP 노드의 키는 '문서ID@v판번호' (예: SOP-COOL-001 2판)
SOP_KEY_COOL_V2 = "____"
MERGE_SOP_APPLIES_TO = """
MATCH (s:SOP {sop_key:$sop_key}), (a:Asset {asset_id:$asset_id})
MERGE (s)-[:APPLIES_TO]->(a)
RETURN s.sop_key + ' -> ' + a.asset_id AS merged
"""

# ---------------------------------------------------------------------------
# [빈칸 2] 질문 1 — 이 설비에는 어떤 센서가 달려 있나?
# ---------------------------------------------------------------------------
Q_ASSET_SENSORS = """
MATCH (a:Asset {asset_id:$asset_id})-[:____]->(s:Sensor)
RETURN s.sensor_id AS sensor_id, s.code AS code, s.quantity AS quantity, s.unit AS unit, s.hz AS hz
ORDER BY s.code
"""

# ---------------------------------------------------------------------------
# [빈칸 3] 질문 2 — 이 설비·사건 유형에 적용되는 '현재 유효한' SOP 와 허용 조치는?
# ---------------------------------------------------------------------------
Q_APPLICABLE_SOP = """
MATCH (sop:SOP)-[:____]->(a:Asset {asset_id:$asset_id})
WHERE sop.status = '____' AND sop.event_type = $event_type
OPTIONAL MATCH (sop)-[:____]->(act:Action)
RETURN sop.doc_id AS doc_id, sop.version AS version, sop.title AS title,
       collect(DISTINCT act.action_id) AS allowed_actions
ORDER BY doc_id
"""

# ---------------------------------------------------------------------------
# [빈칸 4] 질문 3 — 이 사건은 어느 설비에서 났고, 어떤 SOP 절을 근거로 인용했나?
# ---------------------------------------------------------------------------
Q_EVENT_EVIDENCE = """
MATCH (e:Event {event_id:$event_id})-[:____]->(a:Asset)
OPTIONAL MATCH (e)-[:____]->(sec:SOPSection)<-[:____]-(sop:SOP)
RETURN e.event_id AS event_id, a.asset_id AS asset_id, e.event_type AS event_type, e.status AS status,
       collect(DISTINCT sop.doc_id + ' v' + toString(sop.version) + ' §' + sec.section_no) AS citations
"""


# ---------------------------------------------------------------------------
# [빈칸 5] 그래프 결과에 최근 센서 값 붙이기
#   그래프의 sensor_id 는 'HYD-01.TS1', PostgreSQL observation 의 sensor_id 는 'TS1' 이다.
#   두 저장소를 잇는 열쇠는 asset_id 와 센서 코드(code)다.
# ---------------------------------------------------------------------------
def sensors_with_recent_values(asset_id: str, run_id: str, seconds: int = 60) -> list[dict]:
    out = []
    for s in run_read(Q_ASSET_SENSORS, asset_id=asset_id):
        rows = store.recent_window(asset_id, seconds, sensor_id=s[____], run_id=run_id)
        valid = [r for r in rows if r["quality_flag"] == "OK"]
        last = rows[-1] if rows else None
        out.append(
            {
                "sensor_id": s["sensor_id"],
                "unit_graph": s["unit"],
                "unit_db": last["unit"] if last else None,
                "n": len(rows),
                "valid": len(valid),
                "last_value": round(last["raw_value"], 3) if last and last["raw_value"] is not None else None,
                "origin_cycle_id": last["origin_cycle_id"] if last else None,
            }
        )
    return out


# ======================= 아래는 제공 코드 (고치지 않는다) =======================
def run_read(cypher: str, **params) -> list[dict]:
    """읽기 전용 세션으로 질의한다 (쓰기 문장이 섞이면 Neo4j 가 거부한다)."""
    with graph.driver().session(default_access_mode=READ_ACCESS) as s:
        return [r.data() for r in s.run(cypher, **params)]


def merge_if_same_as_seed(cypher: str, **params) -> dict:
    """MERGE 를 트랜잭션 안에서 실행해 보고, 새로 생긴 노드·관계가 없을 때만 반영한다.

    강사 시드와 ID 가 같으면 MERGE 는 기존 노드를 찾기만 하므로 생성 수가 0 이다.
    ID 가 틀리면 새 노드가 생기거나(생성 수 > 0), MATCH 가 아무것도 못 찾아 merged 가 비므로
    되돌리고 committed=False 를 돌려준다.
    """
    with graph.driver().session(default_access_mode=WRITE_ACCESS) as s:
        tx = s.begin_transaction()
        try:
            result = tx.run(cypher, **params)
            merged = [r["merged"] for r in result]
            counters = result.consume().counters
            created = {"merged": merged, "nodes_created": counters.nodes_created, "relationships_created": counters.relationships_created}
            if merged and counters.nodes_created == 0 and counters.relationships_created == 0:
                tx.commit()
                return {**created, "committed": True}
            tx.rollback()
            return {**created, "committed": False}
        finally:
            if not tx.closed():
                tx.rollback()


def seed_check() -> list[dict]:
    """HYD-01 의 세 센서와 SOP-COOL-001 2판 APPLIES_TO 를 시드와 같은 값으로 MERGE 해 본다."""
    results = []
    for sensor in graph.SENSORS:
        r = merge_if_same_as_seed(MERGE_SENSOR, asset_id="HYD-01", **sensor)
        results.append({"what": f"Sensor HYD-01/{sensor['code']}", **r})
    r = merge_if_same_as_seed(MERGE_SOP_APPLIES_TO, sop_key=SOP_KEY_COOL_V2, asset_id="HYD-01")
    results.append({"what": f"{SOP_KEY_COOL_V2} APPLIES_TO HYD-01", **r})
    return results


def any_event_with_citation() -> str | None:
    rows = run_read("MATCH (e:Event)-[:CITES]->(:SOPSection) RETURN e.event_id AS id ORDER BY id DESC LIMIT 1")
    return rows[0]["id"] if rows else None


def load_lab_cycle(asset_id: str = "HYD-01", cycle_id: int = 100) -> str:
    """활동 4 용: UCI 사이클 하나를 LAB-S03- run 으로 적재한다 (재생 시각은 임의의 과거 시각)."""
    from hydops.b2_quality.checks import SensorQualityChecker

    run_id = f"LAB-S03-{uuid.uuid4().hex[:8]}"
    rows = uci.cycle_observations(uci.load_reduced(), cycle_id, asset_id, datetime(2026, 1, 26, 9, 0, tzinfo=timezone.utc))
    store.create_run("uci_replay", "lab-s03", note=f"통합반 S03 사이클 #{cycle_id}", run_id=run_id)
    store.insert_observations(run_id, SensorQualityChecker().check_many(rows))
    return run_id


def cleanup(run_id: str) -> None:
    assert run_id.startswith("LAB-")
    with store.connect() as c:
        c.execute("DELETE FROM observation WHERE run_id = %s", (run_id,))
        c.execute("DELETE FROM run WHERE run_id = %s", (run_id,))


def main() -> None:
    print("① 적재 문장 확인")
    for r in seed_check():
        print("  ", r)
    print("② 질문 1 · HYD-01 센서")
    for r in run_read(Q_ASSET_SENSORS, asset_id="HYD-01"):
        print("  ", r)
    print("③ 질문 2 · 적용 SOP 와 허용 조치")
    for asset_id, event_type in (("HYD-01", "COOLING_ANOMALY"), ("HYD-02", "COOLING_ANOMALY"), ("HYD-03", "COOLING_ANOMALY"), ("HYD-01", "SENSOR_FAULT")):
        rows = run_read(Q_APPLICABLE_SOP, asset_id=asset_id, event_type=event_type)
        print(f"   {asset_id} {event_type}:", [(r["doc_id"], r["version"], r["allowed_actions"]) for r in rows] or "없음")
    event_id = any_event_with_citation()
    print("④ 질문 3 · 사건 근거:", event_id)
    if event_id:
        print("  ", run_read(Q_EVENT_EVIDENCE, event_id=event_id))
    run_id = load_lab_cycle()
    try:
        print("⑤ 관계 + 최근 값:", run_id)
        for r in sensors_with_recent_values("HYD-01", run_id):
            print("  ", r)
    finally:
        cleanup(run_id)
        print("   정리 완료")


if __name__ == "__main__":
    main()
