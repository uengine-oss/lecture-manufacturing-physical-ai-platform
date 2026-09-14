"""S09 · 새 센서 별칭 매핑 (학생 시작본 — 동작하지만 매핑 조건 세 곳이 틀렸다).

원본: lecture/system/hydops/b9_dashboard/app.py 의 PUT /api/sensors/{sensor_id}/aliases 와 POST /api/ingest/{asset_id}.
원본 적재는 매핑 → 품질 검사 → 저장 → 탐지(PlantRuntime.detect)까지 하고 {"inserted", "flags", "events"} 를 돌려준다. 이 복사본은 매핑만 다룬다.
원본은 Neo4j 에서 (:Asset {asset_id})-[:HAS_SENSOR]->(s:Sensor) WHERE s.code=$n OR $n IN s.aliases 로 찾는다.
수업용 복사본은 같은 규칙을 설비 한 대의 센서 목록(메모리)에 적용한다.

asset_sensors 예: [{"sensor_id": "HYD-01.TS1", "code": "TS1", "unit": "°C", "aliases": ["tank_temp"]}, ...]
"""
from __future__ import annotations

from datetime import datetime


class UnknownAliasError(ValueError):
    def __init__(self, unknown: list[str]):
        super().__init__(f"등록되지 않은 센서 별칭: {unknown}")
        self.unknown = unknown


def resolve_sensor(asset_sensors: list[dict], name: str) -> dict | None:
    """표준 코드와 정확히 같거나 등록된 별칭과 정확히 같을 때만 찾는다."""
    for s in asset_sensors:
        # TODO(학생) 1: 대소문자를 무시하고 부분 문자열까지 받아 준다 — 'PS10', 'ts1_backup' 도 매핑된다.
        if s["code"].lower() in name.lower() or any(a.lower() in name.lower() for a in (s.get("aliases") or [])):
            return s
    return None


def alias_conflicts(asset_sensors: list[dict]) -> list[str]:
    """한 설비 안에서 같은 이름이 두 센서를 가리키면 매핑이 모호하다.
    원본 PUT /api/sensors/{sensor_id}/aliases 도 같은 검사로 409 "다른 센서가 이미 쓰는 이름" 을 돌려준다. PUT 은 별칭 목록 전체를 교체한다."""
    owner: dict[str, str] = {}
    conflicts = set()
    for s in asset_sensors:
        for n in [s["code"], *(s.get("aliases") or [])]:
            if n in owner and owner[n] != s["sensor_id"]:
                conflicts.add(n)
            owner.setdefault(n, s["sensor_id"])
    return sorted(conflicts)


def map_gateway_rows(asset_id: str, rows: list[dict], asset_sensors: list[dict]) -> list[dict]:
    """게이트웨이 행 {sensor, ts, value} 를 공통 관측 형식으로 바꾼다. 하나라도 모르는 이름이 있으면 전체를 거부한다."""
    mapped = []
    for r in rows:
        s = resolve_sensor(asset_sensors, r["sensor"])
        if s is None:
            # TODO(학생) 2: 모르는 이름을 조용히 버린다 — 적재 건수만 줄고 아무도 모른다. 전체를 거부해야 한다.
            continue
        mapped.append({
            "asset_id": asset_id,
            "sensor_id": s["code"],
            "ts": datetime.fromisoformat(r["ts"]),
            "elapsed_s": None,
            "origin_cycle_id": None,
            "raw_value": r["value"],
            # TODO(학생) 3: 게이트웨이가 보낸 단위 문자열을 그대로 쓴다 — 표준 센서 단위를 써야 한다.
            "unit": r.get("unit", s["unit"]),
            "agg": None,
            "is_synthetic": True,
        })
    return mapped
