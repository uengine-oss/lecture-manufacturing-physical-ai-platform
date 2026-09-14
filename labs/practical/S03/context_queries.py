"""실전반 S03 · Neo4j 로 설비 관계 연결 (학생 시작본 — # TODO(학생) 표시를 고친다).

세 가지 파라미터 Cypher 질의로 설비 → 센서 / 설비 → 적용 SOP·허용 조치 / 설비 맥락을 조회하고,
asset_id 와 센서 코드로 PostgreSQL 최근 구간 결과와 결합한다. 그래프는 읽기만 한다.
"""
from __future__ import annotations

from datetime import datetime

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b5_detect.detector import recent_summary

# 질의 1 · 설비의 센서 (Resource -HAS_SENSOR-> Measure)
# TODO(학생): 센서 코드만으로 찾아서 세 설비의 센서 9개가 모두 나온다. $asset_id 설비에서 HAS_SENSOR 로 출발하라.
Q_ASSET_SENSORS = """
MATCH (s:Sensor) WHERE s.code IN ['TS1', 'PS1', 'FS1'] AND $asset_id IS NOT NULL
RETURN s.sensor_id AS sensor_id, s.code AS code, s.quantity AS quantity, s.unit AS unit, s.hz AS hz
ORDER BY s.code
"""

# 질의 2 · 사건 유형에 적용되는 최신(active) SOP 와 허용 조치
# TODO(학생): (1) APPLIES_TO 의 도착 설비를 $asset_id 로 묶지 않아 HYD-02 에 HYD-01 SOP 가 섞인다.
#             (2) status 를 거르지 않아 폐기된 SOP-COOL-001 v1 도 나온다.
Q_APPLICABLE_SOP = """
MATCH (sop:SOP)-[:APPLIES_TO]->(a:Asset)
WHERE sop.event_type = $event_type AND $asset_id IS NOT NULL
OPTIONAL MATCH (sop)-[:ALLOWS]->(act:Action)
RETURN DISTINCT sop.doc_id AS doc_id, sop.version AS version, sop.title AS title, sop.approver_role AS approver_role,
       collect(DISTINCT act {.action_id, .min_value, .max_value, .default_value}) AS allowed_actions
ORDER BY doc_id
"""

# 질의 3 · 설비 맥락: 설비 속성 · 냉각 구성품 · 최신 SOP 전체 · 허용 조치 (SOP 가 없어도 설비는 돌려준다)
# TODO(학생): (1) SOP 를 필수 MATCH 로 이어서 SOP 가 없는 신규 설비 HYD-03 이 '설비 없음(found False)'이 된다.
#                 '근거 없음'과 '설비 없음'은 다른 결과다 — OPTIONAL MATCH 로 바꿔라.
#             (2) 최신(active) SOP 만 남겨라.
Q_ASSET_CONTEXT = """
MATCH (a:Asset {asset_id:$asset_id})
OPTIONAL MATCH (a)-[:HAS_COMPONENT]->(c:Component)
MATCH (sop:SOP)-[:APPLIES_TO]->(a)
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
    # TODO(학생): run_id 를 넘기지 않아 수업 서버 시뮬레이터가 쌓는 다른 run 의 관측을 읽는다.
    rows = store.recent_window(asset_id, seconds, until=until)
    summary = recent_summary(rows)
    joined = []
    for s in asset_sensors(asset_id):
        # TODO(학생): 그래프의 전역 ID('HYD-01.TS1')로 관측 요약('TS1')을 찾아 아무것도 결합되지 않는다. 결합 키를 고쳐라.
        obs = summary.get(s["sensor_id"])
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
