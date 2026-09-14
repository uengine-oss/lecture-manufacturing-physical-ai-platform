"""통합반 S05 점검 — SOP 검색 필터, SKILL.md 빈칸, 근거 없는 인용 보류, 역할 구분.

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S05 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
Neo4j·OpenAI 를 쓰지 않는다: 실제 search_sop 코드를 그대로 돌리되, 벡터 저장소와 그래프 조회만
SOP 마크다운(hydops/b6_sop/docs)에서 만든 메모리 사본으로 바꿔 끼운다.
"""
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from hydops.b4_ontology import graph
from hydops.b6_sop import search
from hydops.b7_agent.agent import Proposal, verify_citations
from hydops.config import ROOT

HERE = Path(__file__).resolve().parent
SRC = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
sys.path.insert(0, str(HERE))


def _load(name, base=SRC):
    spec = importlib.util.spec_from_file_location(f"s05_{name}_{id(base)}", base / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load("evidence")
roles = _load("roles")
checker = _load("skill_checker", HERE)

DOCS = graph.load_sop_docs()


# ---- seed_graph 가 만드는 SOPSection 과 같은 메타데이터를 메모리에 만든다 ----------------------------
def section_docs():
    out = []
    for d in DOCS:
        for s in d["sections"]:
            meta = {
                "id": f"{d['sop_key']}#{s['section_no']}", "doc_id": d["doc_id"], "version": d["version"],
                "section_no": s["section_no"], "heading": s["heading"], "status": d["status"],
                "asset_scope": "|" + "|".join(d["applies_to"]) + "|", "event_type": d["event_type"],
            }
            text = f"[{d['doc_id']} v{d['version']} §{s['section_no']} {s['heading']}] {s['text']}"
            out.append(Document(page_content=text, metadata=meta))
    return out


def apply_filter(docs, flt):
    """neo4j_graphrag 의 필터 해석과 같다: $like → CONTAINS (끝의 % 제거), $eq → =."""
    def ok(m):
        for field, cond in flt.items():
            (op, val), = cond.items()
            if op == "$like" and str(val).rstrip("%") not in str(m.get(field, "")):
                return False
            if op == "$eq" and m.get(field) != val:
                return False
            if op not in ("$like", "$eq"):
                return False
        return True
    return [d for d in docs if ok(d.metadata)]


class FakeVectorStore:
    def __init__(self):
        self.filters = []

    def similarity_search_with_score(self, query, k, filter):
        self.filters.append(filter)
        return [(d, 0.5) for d in apply_filter(section_docs(), filter)][:k]


def fake_applicable_sops(asset_id, event_type="COOLING_ANOMALY"):
    return [{"doc_id": d["doc_id"], "version": d["version"], "allowed_actions": []} for d in DOCS
            if asset_id in d["applies_to"] and d["event_type"] == event_type and d["status"] == "active"]


def fake_run(cypher, a=None, t=None, **_):
    return [{"doc_id": d["doc_id"], "version": d["version"]} for d in DOCS if a in d["applies_to"] and d["event_type"] == t]


@pytest.fixture()
def offline_search(monkeypatch):
    vs = FakeVectorStore()
    monkeypatch.setattr(search, "vector_store", lambda: vs)
    monkeypatch.setattr(search, "graph", SimpleNamespace(applicable_sops=fake_applicable_sops, run=fake_run))
    return vs


def keys(hits):
    return {(h["doc_id"], h["version"]) for h in hits}


# ---- 1. 검색 필터 ----------------------------------------------------------------------
@pytest.mark.parametrize("asset_id,sup", [("HYD-01", False), ("HYD-02", False), ("HYD-03", False), ("HYD-01", True)])
def test_filter_equals_system_filter(offline_search, asset_id, sup):
    search.search_sop(asset_id, "COOLING_ANOMALY", k=5, include_superseded=sup)
    assert ev.build_sop_filter(asset_id, sup) == offline_search.filters[-1]


def test_filter_keeps_asset_and_version_apart():
    docs = section_docs()
    h1 = {(d.metadata["doc_id"], d.metadata["version"]) for d in apply_filter(docs, ev.build_sop_filter("HYD-01"))}
    assert ("SOP-COOL-001", 2) in h1 and ("SOP-COOL-001", 1) not in h1, "폐기된 1판이 섞였다"
    assert ("SOP-COOL-002", 1) not in h1, "2호기 SOP 가 1호기 검색에 섞였다"
    h2 = {(d.metadata["doc_id"], d.metadata["version"]) for d in apply_filter(docs, ev.build_sop_filter("HYD-02"))}
    assert ("SOP-COOL-002", 1) in h2 and not any(k[0] in ("SOP-COOL-001", "SOP-LOAD-001") for k in h2)
    assert apply_filter(docs, ev.build_sop_filter("HYD-03")) == [], "3호기에는 등록된 SOP 가 없다"
    hs = {(d.metadata["doc_id"], d.metadata["version"]) for d in apply_filter(docs, ev.build_sop_filter("HYD-01", True))}
    assert ("SOP-COOL-001", 1) in hs


def test_graph_check_removes_other_event_type(offline_search):
    # 메타데이터 필터만으로는 센서 오류 SOP(SOP-SEN-001)도 1호기 냉각 이상 검색에 들어온다
    only_filter = {d.metadata["doc_id"] for d in apply_filter(section_docs(), ev.build_sop_filter("HYD-01"))}
    assert "SOP-SEN-001" in only_filter
    hits = search.search_sop("HYD-01", "COOLING_ANOMALY", k=20)["hits"]
    assert "SOP-SEN-001" not in {h["doc_id"] for h in hits}  # 그래프 APPLIES_TO·event_type 확인이 걸러낸다
    assert search.search_sop("HYD-03", "COOLING_ANOMALY")["hits"] == []


# ---- 2. SKILL.md 빈칸 -------------------------------------------------------------------
def test_provided_system_skill_passes_checker():
    assert checker.check_skill(ROOT / "skills") == []


def test_student_skill_passes_checker():
    problems = checker.check_skill(SRC / "skills")
    assert problems == [], "\n".join(problems)


def test_checker_catches_pinned_section(tmp_path):
    shutil.copytree(ROOT / "skills", tmp_path / "skills")
    p = tmp_path / "skills" / "hydraulic-cooling-response" / "SKILL.md"
    p.write_text(p.read_text().replace("- 검색 결과에 없는 문서·절을 지어내지 않는다.", "- 반드시 SOP-LOAD-001 §4 를 인용한다."))
    assert any("절 번호" in x for x in checker.check_skill(tmp_path / "skills"))


# ---- 3. 근거 없는 인용은 보류 ------------------------------------------------------------
# 실제 검색 결과(HYD-01 냉각 이상 기본 질의, 교재 I05 표)와 센서 오류 검색 결과
HITS_COOL = [("SOP-COOL-001", 2, "2"), ("SOP-COOL-001", 2, "3"), ("SOP-VER-001", 1, "3"), ("SOP-LOAD-001", 1, "2"), ("SOP-LOAD-001", 1, "3")]
HITS_SEN = [("SOP-SEN-001", 1, "3"), ("SOP-SEN-001", 1, "5"), ("SOP-SEN-001", 1, "4"), ("SOP-SEN-001", 1, "6")]


def trace_of(*hit_lists):
    return [{"tool": "search_sop", "args": {}, "result": {"hits": [{"doc_id": d, "version": v, "section": s} for d, v, s in hits]}} for hits in hit_lists]


def cit(*xs):
    return [{"doc_id": d, "version": v, "section": s} for d, v, s in xs]


CASES = [
    ("PROPOSE", cit(("SOP-COOL-001", 2, "2"), ("SOP-LOAD-001", 1, "2")), trace_of(HITS_COOL), "PROPOSE"),
    ("PROPOSE", cit(("SOP-LOAD-001", 1, "4")), trace_of(HITS_COOL), "HOLD"),  # 실제 문서에 있지만 이번 검색에 안 나온 절
    ("PROPOSE", cit(("SOP-FAKE-9", 1, "4")), trace_of(HITS_COOL), "HOLD"),  # 지어낸 문서
    ("PROPOSE", cit(("SOP-COOL-001", 1, "2")), trace_of(HITS_COOL), "HOLD"),  # 버전이 다르다
    ("PROPOSE", [], trace_of(HITS_COOL), "HOLD"),  # 인용 없음
    ("HOLD", [], [], "HOLD"),  # HYD-03: 검색 결과 없음
    ("SENSOR_CHECK", cit(("SOP-SEN-001", 1, "4"), ("SOP-SEN-001", 1, "3")), trace_of(HITS_SEN), "SENSOR_CHECK"),
]


@pytest.mark.parametrize("decision,citations,trace,expected", CASES)
def test_citation_check_matches_verify_citations(decision, citations, trace, expected):
    got = ev.decide_after_citation_check(decision, citations, trace)
    real, _ = verify_citations(Proposal(decision=decision, citations=citations, rationale="-"), trace)
    assert got == real.decision == expected


def test_retrieved_keys():
    assert ev.retrieved_keys(trace_of(HITS_SEN)) == set(HITS_SEN)
    assert ev.retrieved_keys([{"tool": "get_asset_context", "result": {"hits": [{"doc_id": "X", "version": 1, "section": "1"}]}}]) == set()


# ---- 4. 역할 구분 -----------------------------------------------------------------------
def test_roles():
    vals = list(roles.ROLE.values())
    assert vals == ["FORECAST", "DETECT", "EVIDENCE", "GUIDE", "TOOL"]
    assert roles.EVENT_PATH == "DETECT", "사건은 규칙·이동 통계 감지가 만든다 (zero-shot 은 선택 비교)"
    assert roles.SKILL_IS_CITABLE is False
