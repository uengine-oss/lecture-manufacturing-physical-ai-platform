"""실전반 S03 · Neo4j 로 설비 관계 연결 (정답본).

세 가지 파라미터 Cypher 질의로 설비 → 센서 / 설비 → 적용 SOP·허용 조치 / 설비 맥락을 조회하고,
asset_id 와 센서 코드로 PostgreSQL 최근 구간 결과와 결합한다. 그래프는 읽기만 한다.
"""
from __future__ import annotations

from datetime import datetime

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b5_detect.detector import recent_summary

# 질의 1 · 설비의 센서 (Resource -HAS_SENSOR-> Measure)
Q_ASSET_SENSORS = """
MATCH (a:Asset {asset_id:$asset_id})-[:HAS_SENSOR]->(s:Sensor)
RETURN s.sensor_id AS sensor_id, s.code AS code, s.quantity AS quantity, s.unit AS unit, s.hz AS hz
ORDER BY s.code
"""

# 질의 2 · 사건 유형에 적용되는 최신(active) SOP 와 허용 조치
Q_APPLICABLE_SOP = """
MATCH (sop:SOP)-[:APPLIES_TO]->(a:Asset {asset_id:$asset_id})
WHERE sop.status = 'active' AND sop.event_type = $event_type
OPTIONAL MATCH (sop)-[:ALLOWS]->(act:Action)
RETURN sop.doc_id AS doc_id, sop.version AS version, sop.title AS title, sop.approver_role AS approver_role,
       collect(DISTINCT act {.action_id, .min_value, .max_value, .default_value}) AS allowed_actions
ORDER BY doc_id
"""

# 질의 3 · 설비 맥락: 설비 속성 · 냉각 구성품 · 최신 SOP 전체 · 허용 조치 (SOP 가 없어도 설비는 돌려준다)
Q_ASSET_CONTEXT = """
MATCH (a:Asset {asset_id:$asset_id})
OPTIONAL MATCH (a)-[:HAS_COMPONENT]->(c:Component)
OPTIONAL MATCH (sop:SOP)-[:APPLIES_TO]->(a)
WHERE sop.status = 'active'
OPTIONAL MATCH (sop)-[:ALLOWS]->(act:Action)
RETURN a {.asset_id, .name, .cooling, .line} AS asset, c.component_id AS component,
       collect(DISTINCT sop.doc_id + '@v' + toString(sop.version)) AS active_sops,
       collect(DISTINCT act.action_id) AS allowed_actions
"""


def asset_sensors(asset_id: str) -> list[dict]:
    return graph.run(Q_ASSET_SENSORS, asset_id=asset_id)


def applicable_sops(asset_id: str, event_type: str) -> list[dict]:
    rows = graph.run(Q_APPLICABLE_SOP, asset_id=asset_id, event_type=event_type)
    for r in rows:
        r["allowed_actions"] = [a for a in r["allowed_actions"] if a and a.get("action_id")]
    return rows


def asset_context(asset_id: str) -> dict:
    rows = graph.run(Q_ASSET_CONTEXT, asset_id=asset_id)
    if not rows:
        return {"asset_id": asset_id, "found": False}
    r = rows[0]
    return {
        "asset_id": asset_id,
        "found": True,
        "asset": r["asset"],
        "component": r["component"],
        "active_sops": sorted(r["active_sops"]),
        "allowed_actions": sorted(r["allowed_actions"]),
    }


def join_recent(asset_id: str, run_id: str | None, seconds: int = 60, until: datetime | None = None) -> dict:
    """그래프의 센서 목록(sensor_id, code, unit)과 PostgreSQL 최근 구간 요약을 결합한다.

    결합 키: 설비는 asset_id, 센서는 그래프 Sensor.code == observation.sensor_id.
    그래프 Sensor.sensor_id 는 'HYD-01.TS1' 처럼 설비가 붙은 전역 ID 라 관측 테이블의 'TS1' 과 다르다.
    """
    rows = store.recent_window(asset_id, seconds, run_id=run_id, until=until)
    summary = recent_summary(rows)
    joined = []
    for s in asset_sensors(asset_id):
        obs = summary.get(s["code"])
        joined.append(
            {
                "sensor_id": s["sensor_id"],
                "code": s["code"],
                "quantity": s["quantity"],
                "unit_graph": s["unit"],
                "unit_obs": obs["unit"] if obs else None,
                "unit_match": bool(obs) and obs["unit"] == s["unit"],
                "samples": obs["samples"] if obs else 0,
                "valid_ratio": obs["quality"]["valid_ratio"] if obs else None,
                "valid_mean": obs["valid_mean"] if obs else None,
                "last_valid": obs["last_valid"] if obs else None,
                "sensor_state": obs.get("sensor_state") if obs else None,
            }
        )
    return {
        "asset_id": asset_id,
        "run_id": run_id,
        "context": asset_context(asset_id),
        "cooling_sops": applicable_sops(asset_id, "COOLING_ANOMALY"),
        "sensors": joined,
    }
