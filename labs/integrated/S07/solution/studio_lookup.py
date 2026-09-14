"""통합반 7회 실습 — 교육용 플랫폼(Lab Platform) Ontology Studio 조회 도우미.

빈칸(____)을 채운다. 이 파일은 GET 만 호출한다 (발행·시작·주입을 하지 않는다).
"""
from __future__ import annotations

import httpx

____ = None  # 빈칸 표시 — 오른쪽 값을 채운다

PLATFORM_API = "http://localhost:8910"   # 교육용 플랫폼 주소
HYDOPS_API = "http://localhost:8800"     # 로컬 관제 API 주소 (대조용)
SCHEMA_NAME = "HydraulicOps"             # 수업용 스키마 이름
NOT_PUBLISHED_STATUS = 409               # 발행 전 객체 조회가 돌려주는 HTTP 상태 코드 (S12 화면)


def related_url(cls: str, key: str, rel: str) -> str:
    """관계 조회 주소: GET /studio/schemas/{스키마}/objects/{클래스}/{키}/related/{관계}"""
    return f"{PLATFORM_API}/studio/schemas/{SCHEMA_NAME}/objects/{cls}/{key}/related/{rel}"


def get_related(cls: str, key: str, rel: str) -> dict:
    r = httpx.get(related_url(cls, key, rel), timeout=30)
    body = r.json()
    return {"http_status": r.status_code, **(body if isinstance(body, dict) else {})}


def classify(result: dict) -> str:
    """조회 결과를 세 가지로 나눈다.

    NOT_PUBLISHED      발행 전이라 조회 자체가 거부됨
    PUBLISHED_NO_DATA  발행은 됐지만 조건에 맞는 행·노드가 0개
    HAS_DATA           실제 데이터가 있음
    """
    if result.get("http_status") == NOT_PUBLISHED_STATUS:
        return "NOT_PUBLISHED"
    if result.get("http_status") != 200:
        return "ERROR"
    if result.get("count", 0) == 0:
        return "PUBLISHED_NO_DATA"
    return "HAS_DATA"


def local_asset(asset_id: str) -> dict:
    """로컬 관제 API 의 설비 맥락 (hydops graph.asset_context)"""
    rows = httpx.get(f"{HYDOPS_API}/api/assets", timeout=30).json()
    return next(a for a in rows if a["asset_id"] == asset_id)


def same_sensors(local: dict, platform_related: dict) -> bool:
    """로컬 화면의 센서 ID 목록과 플랫폼 HAS_SENSOR 조회 결과가 같은지 대조한다."""
    local_ids = sorted(s["sensor_id"] for s in local["sensors"])
    platform_ids = sorted(o["sensor_id"] for o in platform_related["objects"])
    return local_ids == platform_ids


if __name__ == "__main__":
    for cls, key, rel in [("Asset", "HYD-01", "HAS_SENSOR"), ("Asset", "HYD-01", "HAS_EVENT"), ("Asset", "HYD-02", "HAS_EVENT"), ("Asset", "HYD-03", "GOVERNED_BY")]:
        res = get_related(cls, key, rel)
        print(f"{cls}:{key} -{rel}-> {classify(res):18s} count={res.get('count')} note={res.get('note')}")
    print("HYD-01 센서 대조:", same_sensors(local_asset("HYD-01"), get_related("Asset", "HYD-01", "HAS_SENSOR")))
