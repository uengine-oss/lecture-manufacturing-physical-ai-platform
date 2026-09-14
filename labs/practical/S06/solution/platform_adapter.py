"""S06 · 플랫폼 어댑터 — 에이전트의 설비 맥락 조회를 교육용 플랫폼(Lab Platform) Ontology Studio 로 바꾼다 (정답본).

원본(로컬): lecture/system/hydops/b4_ontology/graph.py 의 asset_context(asset_id)
플랫폼 API: lecture/system/labplatform/studio.py
  POST /studio/schemas/{schema}/objects/{class}/fetch            {filters, limit}
  GET  /studio/schemas/{schema}/objects/{class}/{key}/related/{rel}
  POST /studio/schemas/{schema}/objects/{class}/behaviors/{b}/invoke {arguments}
이미 발행된 스키마 HydraulicOps 를 읽기만 한다. 발행·가져오기는 하지 않는다.
"""
from __future__ import annotations

import contextlib
import os
from urllib.parse import quote

import httpx

PLATFORM_URL = os.environ.get("LAB_PLATFORM_URL", "http://localhost:8910")
SCHEMA = os.environ.get("LAB_SCHEMA_NAME", "HydraulicOps")

# 로컬 asset_context 가 돌려주는 모양 (이 키들을 똑같이 채운다)
SOP_FIELDS = ("doc_id", "version", "title", "effective_date", "approver_role")
ACTION_FIELDS = ("action_id", "name", "min_value", "max_value", "default_value", "requires_approval")
# 로컬 asset_context 는 COOLING_ANOMALY 와 SENSOR_FAULT SOP 만 모은다
EVENT_TYPES = ("COOLING_ANOMALY", "SENSOR_FAULT")


class PlatformError(RuntimeError):
    pass


class PlatformContext:
    def __init__(self, base_url: str = PLATFORM_URL, schema: str = SCHEMA, client: httpx.Client | None = None):
        self.base = f"{base_url.rstrip('/')}/studio/schemas/{schema}"
        self.client = client or httpx.Client(timeout=15)
        self.calls: list[str] = []  # 어떤 API 를 몇 번 불렀는지 (비교 보고에 쓴다)

    # ---- 제공: API 호출 --------------------------------------------------------------
    def _json(self, r: httpx.Response) -> dict:
        self.calls.append(f"{r.request.method} {r.request.url.path}")
        if r.status_code == 409:
            raise PlatformError(f"발행되지 않은 스키마 — {r.json().get('detail')}")
        if r.status_code >= 400:
            raise PlatformError(f"{r.status_code} {r.text[:200]}")
        return r.json()

    def fetch(self, cname: str, filters: dict | None = None, limit: int = 50) -> dict:
        return self._json(self.client.post(f"{self.base}/objects/{cname}/fetch", json={"filters": filters or {}, "limit": limit}))

    def related(self, cname: str, key: str, rel: str) -> dict:
        return self._json(self.client.get(f"{self.base}/objects/{cname}/{quote(key, safe='')}/related/{rel}"))

    def invoke(self, cname: str, behavior: str, arguments: dict) -> dict:
        return self._json(self.client.post(f"{self.base}/objects/{cname}/behaviors/{behavior}/invoke", json={"arguments": arguments}))

    # ---- 학생 구현 --------------------------------------------------------------------
    def asset_context(self, asset_id: str) -> dict:
        """graph.asset_context(asset_id) 와 같은 모양을 플랫폼 조회만으로 만든다."""
        found = self.fetch("Asset", {"asset_id": asset_id}, limit=1)
        if found["count"] == 0:
            return {"asset_id": asset_id, "found": False}

        sensors = sorted(self.related("Asset", asset_id, "HAS_SENSOR")["objects"], key=lambda s: s["code"])

        # 설비에 적용되는 SOP 는 관계(GOVERNED_BY = APPLIES_TO 역방향, active 만)로 찾는다.
        # SOP 클래스 전체를 status 로만 fetch 하면 다른 설비의 SOP 가 섞인다.
        sops = [s for s in self.related("Asset", asset_id, "GOVERNED_BY")["objects"] if s.get("event_type") in EVENT_TYPES]
        sops.sort(key=lambda s: (EVENT_TYPES.index(s["event_type"]), s["doc_id"]))

        allowed: dict[str, dict] = {}
        for s in sops:
            for a in self.related("SOP", s["sop_key"], "ALLOWS")["objects"]:
                allowed.setdefault(a["action_id"], {k: a.get(k) for k in ACTION_FIELDS})

        return {
            "asset_id": asset_id,
            "found": True,
            "asset": found["objects"][0],
            "sensors": sensors,
            # 발행된 SOP 클래스에는 effective_date·approver_role 속성이 없다 → None 으로 두고 비교에서 드러낸다
            "applicable_sops": [{k: s.get(k) for k in SOP_FIELDS} for s in sops],
            "allowed_actions": list(allowed.values()),
            "source": "platform",
        }

    def recent_state(self, asset_id: str) -> list[dict]:
        """Behavior Asset.recent_state — 최근 60초 센서별 유효 통계 (원천 DB 가상 연결)."""
        return self.invoke("Asset", "recent_state", {"asset_id": asset_id})["rows"]


def local_context(asset_id: str) -> dict:
    from hydops.b4_ontology import graph

    return graph.asset_context(asset_id)


def compare_contexts(local: dict, platform: dict) -> dict:
    """같은 asset_id 의 로컬·플랫폼 맥락을 대조한다.

    match 는 '에이전트 판단에 쓰는 내용'(센서·적용 SOP·허용 조치와 값 범위)이 같은지로 본다.
    한쪽에만 있는 속성(발행 클래스에 없는 속성)은 field_gaps 로 따로 보고한다 — 불일치와 구분한다.
    """
    out: dict = {"asset_id": local.get("asset_id"), "found": [bool(local.get("found")), bool(platform.get("found"))]}
    if not local.get("found") or not platform.get("found"):
        out.update(match=local.get("found") == platform.get("found"), sensors_equal=None, sops_equal=None, actions_equal=None, only_local={}, only_platform={}, field_gaps=[])
        return out

    def sensor_keys(c):
        return {(s["sensor_id"], s["code"], s["unit"]) for s in c["sensors"]}

    def sop_keys(c):
        return {(s["doc_id"], int(s["version"])) for s in c["applicable_sops"]}

    def action_keys(c):
        return {(a["action_id"], a.get("min_value"), a.get("max_value"), a.get("default_value")) for a in c["allowed_actions"]}

    diffs = {}
    for name, fn in (("sensors", sensor_keys), ("sops", sop_keys), ("actions", action_keys)):
        lo, pl = fn(local), fn(platform)
        out[f"{name}_equal"] = lo == pl
        diffs[name] = (sorted(lo - pl), sorted(pl - lo))
    out["only_local"] = {k: v[0] for k, v in diffs.items() if v[0]}
    out["only_platform"] = {k: v[1] for k, v in diffs.items() if v[1]}

    gaps = set()
    for k, v in local["asset"].items():
        if k not in platform["asset"]:
            gaps.add(f"asset.{k}")
    for s in local["applicable_sops"]:
        p = next((x for x in platform["applicable_sops"] if (x["doc_id"], int(x["version"])) == (s["doc_id"], int(s["version"]))), None)
        if p:
            gaps |= {f"applicable_sops.{k}" for k in SOP_FIELDS if s.get(k) is not None and p.get(k) is None}
    out["field_gaps"] = sorted(gaps)
    out["match"] = out["sensors_equal"] and out["sops_equal"] and out["actions_equal"]
    return out


# ---- 제공: 에이전트의 맥락 조회를 바꿔 끼운다 (시스템 파일은 고치지 않는다) --------------
@contextlib.contextmanager
def use_context_provider(provider):
    """hydops.b7_agent.tools.get_asset_context_impl 를 잠시 provider 로 바꾼다.

    build_tools() 안의 get_asset_context 도구는 호출 시점에 이 모듈 전역 이름을 찾으므로,
    같은 에이전트 코드가 로컬 대신 플랫폼을 조회하게 된다.
    """
    from hydops.b7_agent import tools as T

    original = T.get_asset_context_impl
    T.get_asset_context_impl = provider
    try:
        yield
    finally:
        T.get_asset_context_impl = original
