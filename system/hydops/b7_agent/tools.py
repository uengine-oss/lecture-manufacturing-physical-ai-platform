"""B7 · 에이전트 도구. 타입이 있는 함수를 에이전트가 호출할 수 있게 연결한다.

같은 함수 본체를 LangChain 도구, MCP 서버, 교육용 플랫폼이 공유한다 (도구 계약 표).
"""
from __future__ import annotations

import json
from datetime import datetime

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b5_detect.detector import recent_summary
from hydops.b6_sop.search import search_sop as _search_sop
from hydops.b8_action import executor


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))


class Citation(BaseModel):
    doc_id: str = Field(description="SOP 문서 ID, 예: SOP-COOL-001")
    version: int = Field(description="SOP 버전")
    section: str = Field(description="절 번호, 예: '4'")


# ---- 본체 (플랫폼·MCP 에서 재사용) ----------------------------------------------
def get_asset_context_impl(asset_id: str) -> dict:
    return graph.asset_context(asset_id)


def get_recent_window_impl(asset_id: str, seconds: int = 60, until: datetime | None = None, run_id: str | None = None) -> dict:
    rows = store.recent_window(asset_id, seconds, until=until, run_id=run_id)
    return {"asset_id": asset_id, "seconds": seconds, "sensors": recent_summary(rows)}


def search_sop_impl(asset_id: str, event_type: str, query: str | None = None) -> dict:
    res = _search_sop(asset_id, event_type, query, k=5)
    return res


def propose_action_impl(event_id: str, action_id: str, value: float | None, citations: list[dict]) -> dict:
    return executor.propose_action(event_id, action_id, value, citations)


def build_tools(event_until: datetime | None = None, run_id: str | None = None, trace: list | None = None):
    """에이전트에 등록할 LangChain 도구 목록. trace 에 호출 이력을 남긴다 (B9 에서 표시)."""
    trace = trace if trace is not None else []

    def log(name, args, result):
        trace.append({"tool": name, "args": args, "result": result})
        return _dump(result)

    @tool
    def get_asset_context(asset_id: str) -> str:
        """설비의 센서 목록, 적용 SOP(문서 ID·버전), 허용 조치와 값 범위를 조회한다."""
        return log("get_asset_context", {"asset_id": asset_id}, get_asset_context_impl(asset_id))

    @tool
    def get_recent_window(asset_id: str, seconds: int = 60) -> str:
        """설비의 최근 구간 관측 요약(센서별 단위·품질 플래그·유효 통계·지속 이상 여부)을 조회한다. 원시 배열은 주지 않는다."""
        return log("get_recent_window", {"asset_id": asset_id, "seconds": seconds}, get_recent_window_impl(asset_id, seconds, until=event_until, run_id=run_id))

    @tool
    def search_sop(asset_id: str, event_type: str, query: str = "") -> str:
        """설비에 적용되는 최신(active) SOP 절을 검색한다. event_type 은 COOLING_ANOMALY 또는 SENSOR_FAULT."""
        return log("search_sop", {"asset_id": asset_id, "event_type": event_type, "query": query}, search_sop_impl(asset_id, event_type, query or None))

    @tool
    def propose_action(event_id: str, action_id: str, value: float | None, citations: list[Citation]) -> str:
        """조치 제안의 허용 범위를 검사한다 (허용 조치·값 범위·근거·중복 실행). 실행하지 않는다."""
        cits = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in citations]
        return log("propose_action", {"event_id": event_id, "action_id": action_id, "value": value, "citations": cits}, propose_action_impl(event_id, action_id, value, cits))

    return [get_asset_context, get_recent_window, search_sop, propose_action]
