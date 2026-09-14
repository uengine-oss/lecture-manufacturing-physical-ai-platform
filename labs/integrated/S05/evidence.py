"""S05 · SOP 검색 필터와 근거 확인 — 빈칸 ____ 을 채운다.

- build_sop_filter : hydops/b6_sop/search.py 의 search_sop 가 Neo4jVector 에 넘기는 메타데이터 필터
- retrieved_keys   : 이번 실행에서 search_sop 가 실제로 돌려준 절의 (doc_id, version, section)
- decide_after_citation_check : 인용이 검색 결과에 없으면 HOLD (hydops/b7_agent/agent.py 의 verify_citations 와 같은 규칙)
"""

____ = None  # 빈칸 표시


def build_sop_filter(asset_id: str, include_superseded: bool = False) -> dict:
    # 적용 설비: SOPSection.asset_scope 는 "|HYD-01|HYD-02|" 모양 → 양쪽 | 까지 포함해 '포함' 검사
    flt = {"asset_scope": {"____": f"|{____}|"}}
    # 버전: 폐기(superseded)된 판을 빼고 유효(active) 판만
    if not include_superseded:
        flt["____"] = {"$eq": "____"}
    return flt


def retrieved_keys(trace: list[dict]) -> set:
    return {
        (h["doc_id"], int(h["version"]), str(h["____"]))
        for t in trace
        if t["tool"] == "____"
        for h in t["result"]["hits"]
    }


def decide_after_citation_check(decision: str, citations: list[dict], trace: list[dict]) -> str:
    """제안(PROPOSE)·센서 점검(SENSOR_CHECK)은 인용이 하나 이상 있고, 모두 검색 결과에 있어야 한다."""
    keys = retrieved_keys(trace)
    missing = [c for c in citations if (c["doc_id"], int(c["version"]), str(c["section"])) not in keys]
    if decision in ("PROPOSE", "SENSOR_CHECK") and (missing or not citations):
        return "____"
    return decision
