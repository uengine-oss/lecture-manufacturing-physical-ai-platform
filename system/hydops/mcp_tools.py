"""MCP 도구 서버 — 실라버스 '도구 계약' 표의 6개 도구.

교육용 플랫폼의 업무 에이전트·프로세스가 streamable HTTP 로 호출한다 (http://localhost:8800/mcp/).
도구의 입력·출력과 오류를 그대로 드러낸다. 승인은 도구가 아니다 — 승인은 사람 태스크가 기록한다.
"""
from __future__ import annotations

import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from hydops.b3_tsdb import store
from hydops.b7_agent import tools as T
from hydops.b8_action import service


def _j(o):
    return json.loads(json.dumps(o, ensure_ascii=False, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x)))


class Citation(BaseModel):
    doc_id: str = Field(description="SOP 문서 ID")
    version: int = Field(description="SOP 버전")
    section: str = Field(description="절 번호")


def build_mcp(get_runtime) -> FastMCP:
    mcp = FastMCP("hydops-tools", stateless_http=True, streamable_http_path="/", json_response=True)

    @mcp.tool()
    def get_asset_context(asset_id: str) -> dict:
        """설비의 센서·적용 SOP·허용 조치를 조회한다."""
        return _j(T.get_asset_context_impl(asset_id))

    @mcp.tool()
    def get_recent_window(asset_id: str, seconds: int = 60, event_id: str = "") -> dict:
        """최근 구간의 관측 요약(단위·품질 플래그·유효 통계·지속 이상 여부)을 조회한다.
        event_id 를 주면 그 사건의 실행(run_id)과 탐지 구간 끝 시각을 기준으로 잘라, 나중에 다시 불러도 같은 근거를 본다."""
        ev = store.get_event(event_id) if event_id else None
        until, run_id = (ev["window_end"], ev["run_id"]) if ev else (None, None)
        out = T.get_recent_window_impl(asset_id, seconds, until=until, run_id=run_id)
        out["pinned_to_event"] = bool(ev)
        return _j(out)

    @mcp.tool()
    def search_sop(asset_id: str, event_type: str, query: str = "") -> dict:
        """적용 설비·최신 버전으로 필터한 SOP 절(문서 ID·버전·절·근거 본문)을 검색한다."""
        return _j(T.search_sop_impl(asset_id, event_type, query or None))

    @mcp.tool()
    def propose_action(event_id: str, action_id: str, value: float, citations: list[Citation]) -> dict:
        """제안의 허용 범위 검사 결과를 돌려준다. 실행하지 않는다. 값이 없는 조치는 value=0 으로 보낸다."""
        return _j(T.propose_action_impl(event_id, action_id, value, [c.model_dump() for c in citations]))

    @mcp.tool()
    def execute_sim_action(event_id: str, approval_id: str, action_id: str, value: float, approved: bool | None = None) -> dict:
        """실제 승인 기록(approval_id)을 검사한 뒤 시뮬레이터에 조치를 실행하고 결과를 기록한다.
        approved 인자는 참고로만 기록하며 승인으로 인정하지 않는다."""
        ev = store.get_event(event_id)
        if ev is None:
            return {"ok": False, "refused": "EVENT_NOT_FOUND"}
        claims = {"approved": approved} if approved is not None else {}
        return _j(service.execute(get_runtime().sims[ev["asset_id"]], event_id, approval_id or None, action_id, value, **claims))

    @mcp.tool()
    def verify_recovery(event_id: str, action_log_id: str, window_index: int = 0) -> dict:
        """조치 이후 재측정 창으로 회복·미개선·데이터 부족을 판정한다. 시각 전이면 ready=false 와 wait_until."""
        ev = store.get_event(event_id)
        rt = get_runtime()
        return _j(service.verify(event_id, action_log_id, window_index, now=rt.now(ev["asset_id"])))

    return mcp
