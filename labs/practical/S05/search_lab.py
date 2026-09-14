"""S05 · SOP 절 검색 필터와 근거 검증 (학생 시작본).

원본: lecture/system/hydops/b6_sop/search.py (search_sop), hydops/b7_agent/agent.py (verify_citations, run_offline_agent).
시스템 코드는 고치지 않는다. 검색을 세 부분(필터 만들기 → 벡터 후보 → 그래프 확인)으로 나눠 옮겼다.

retrieve 함수 계약: retrieve(query, k, flt) -> [(metadata: dict, text: str, score: float), ...]
  metadata 키: id, doc_id, version, section_no, heading, status, asset_scope, event_type
  기본값은 시스템의 Neo4jVector(similarity_search_with_score). 테스트는 같은 필터 의미($like=CONTAINS, $eq)를
  지키는 오프라인 검색기를 넣는다.
"""
from __future__ import annotations

from hydops.b4_ontology import graph
from hydops.b7_agent.agent import Proposal

DEFAULT_QUERY = {
    "COOLING_ANOMALY": "온도 60도 초과 지속 냉각 이상 발동 조건 허용 조치 승인 부하 감소 재점검",
    "SENSOR_FAULT": "센서 결측 고착 품질 플래그 센서 점검 설비 조치 보류",
}


# ---- 1. 메타데이터 필터 ---------------------------------------------------------------
def build_filter(asset_id: str, include_superseded: bool = False) -> dict:
    """벡터 검색 전에 거르는 조건. asset_scope 는 '|HYD-01|HYD-02|' 모양으로 저장돼 있다."""
    # TODO(학생): (1) asset_scope 는 '|HYD-01|HYD-02|' 모양이다. 경계 문자 | 없이 CONTAINS 로 찾으면
    #               'HYD-1' 이 'HYD-10' 에도 걸린다. |asset_id| 로 고친다.
    #            (2) 폐기본(status='superseded')이 섞인다. include_superseded 가 False 면 status 가 active 인 절만 남긴다.
    flt: dict = {"asset_scope": {"$like": asset_id}}
    return flt


# ---- 2. 그래프 확인 ---------------------------------------------------------------------
def applicable_keys(asset_id: str, event_type: str, include_superseded: bool = False) -> set[tuple[str, int]]:
    """(SOP)-[:APPLIES_TO]->(Asset) 관계가 실제로 있고 사건 유형이 맞는 (doc_id, version)."""
    keys = {(s["doc_id"], int(s["version"])) for s in graph.applicable_sops(asset_id, event_type)}
    if include_superseded:
        keys |= {
            (r["doc_id"], int(r["version"]))
            for r in graph.run(
                "MATCH (s:SOP)-[:APPLIES_TO]->(:Asset {asset_id:$a}) WHERE s.event_type=$t RETURN s.doc_id AS doc_id, s.version AS version",
                a=asset_id,
                t=event_type,
            )
        }
    return keys


def confirm_with_graph(candidates: list[tuple[dict, str, float]], asset_id: str, event_type: str, k: int = 4, include_superseded: bool = False) -> list[dict]:
    """벡터 후보 중 그래프로 확인된 절만 k 개까지 남긴다. 같은 절은 한 번만."""
    # TODO(학생): 지금은 벡터 후보를 그대로 k 개 자른다. 메타데이터 필터는 설비·버전만 거르므로
    #            다른 사건 유형(SENSOR_FAULT) 절이나 APPLIES_TO 관계가 없는 절이 근거로 들어온다.
    #            applicable_keys(...) 에 있는 (doc_id, version) 만 남기고, 같은 절(meta["id"])은 한 번만 넣는다.
    hits = []
    for meta, text, score in candidates:
        hits.append({"doc_id": meta["doc_id"], "version": int(meta["version"]), "section": str(meta["section_no"]), "heading": meta["heading"], "score": round(float(score), 4), "text": text})
        if len(hits) >= k:
            break
    return hits


# ---- 제공: 검색 조립 ----------------------------------------------------------------------
def neo4j_retrieve(query: str, k: int, flt: dict):
    from hydops.b6_sop.search import vector_store

    return [(d.metadata, d.page_content, s) for d, s in vector_store().similarity_search_with_score(query, k=k, filter=flt)]


def search_sop_lab(asset_id: str, event_type: str, query: str | None = None, k: int = 4, include_superseded: bool = False, retrieve=None) -> dict:
    retrieve = retrieve or neo4j_retrieve
    query = query or DEFAULT_QUERY.get(event_type, event_type)
    flt = build_filter(asset_id, include_superseded)
    candidates = retrieve(query, k * 3, flt)
    return {"asset_id": asset_id, "event_type": event_type, "query": query, "filter": flt, "hits": confirm_with_graph(candidates, asset_id, event_type, k, include_superseded)}


# ---- 3. 근거 검증 -------------------------------------------------------------------------
def verify_citations_lab(p: Proposal, trace: list[dict]) -> tuple[Proposal, list[str]]:
    """인용은 이번 실행의 search_sop 결과(hits)에 (doc_id, version, section) 이 모두 같은 절로 나와야 한다."""
    # TODO(학생): (1) 지금은 doc_id 만 비교한다. 검색된 적 없는 버전·절(예: SOP-COOL-001 v1 §4)도 통과한다.
    #               (doc_id, version, section) 세 값이 모두 같은 절만 인정한다.
    #            (2) 인용이 하나도 없는 PROPOSE·SENSOR_CHECK 도 HOLD 로 바꿔야 한다.
    retrieved = {h["doc_id"] for t in trace if t["tool"] == "search_sop" for h in t["result"]["hits"]}
    problems = [f"{c.doc_id}@v{c.version}#{c.section}" for c in p.citations if c.doc_id not in retrieved]
    if p.decision in ("PROPOSE", "SENSOR_CHECK") and problems:
        return Proposal(decision="HOLD", action_id=p.action_id, value=p.value, citations=[], rationale=f"근거 검증 실패로 보류: 검색되지 않은 인용 {problems or '없음'}"), problems
    return p, problems


# ---- 제공: 오프라인 에이전트 (Skill 순서를 코드로 따른다, DB 사건 없이) ---------------------
def offline_proposal(asset_id: str, event_type: str, sensor_state: str = "VALID", retrieve=None) -> dict:
    """run_offline_agent 와 같은 순서: 센서 품질 → 설비 맥락 → SOP 검색 → 제안 → 근거 검증.

    propose_action(허용 범위 검사)은 DB 의 사건이 필요하므로 여기서는 값 범위만 코드로 확인한다.
    """
    trace: list[dict] = []
    if event_type == "SENSOR_FAULT" or sensor_state == "SENSOR_FAULT":
        sop = search_sop_lab(asset_id, "SENSOR_FAULT", retrieve=retrieve)
        trace.append({"tool": "search_sop", "result": sop})
        cits = [{"doc_id": h["doc_id"], "version": h["version"], "section": h["section"]} for h in sop["hits"][:2]]
        raw = Proposal(decision="SENSOR_CHECK", action_id="SENSOR_CHECK", citations=cits, rationale="온도 센서 품질 불량으로 설비 조치를 보류하고 센서 점검을 제안한다.", checks_passed=bool(cits)) if cits else Proposal(decision="HOLD", rationale="센서 오류 SOP 근거가 없어 보류한다.")
    else:
        ctx = graph.asset_context(asset_id)
        trace.append({"tool": "get_asset_context", "result": ctx})
        sop = search_sop_lab(asset_id, event_type, retrieve=retrieve)
        trace.append({"tool": "search_sop", "result": sop})
        equipment = [x for x in ctx.get("allowed_actions", []) if x.get("requires_approval") and x.get("default_value") is not None]
        if not sop["hits"] or not equipment:
            raw = Proposal(decision="HOLD", rationale="이 설비에 적용되는 냉각 이상 SOP 근거나 허용 조치가 없어 보류한다.")
        else:
            act = equipment[0]
            cits = [{"doc_id": h["doc_id"], "version": h["version"], "section": h["section"]} for h in sop["hits"][:3]]
            in_range = act["min_value"] <= act["default_value"] <= act["max_value"]
            raw = Proposal(decision="PROPOSE" if in_range else "HOLD", action_id=act["action_id"], value=act["default_value"], citations=cits, rationale=f"적용 SOP 가 {act['name']}을(를) 허용한다.", checks_passed=in_range)
    final, problems = verify_citations_lab(raw, trace)
    return {"raw": raw.model_dump(), "final": final.model_dump(), "citation_problems": problems, "trace": trace}
