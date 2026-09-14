"""실전반 S05 확인 테스트 — SOP 검색 필터·그래프 확인·근거 검증·SKILL.md 규칙.

학생 파일 확인: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S05 -q
정답본 확인:   LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S05 -q

HYDOPS_AGENT_MODE=offline 으로 돈다. OpenAI 를 부르지 않는다.
Neo4j 는 SOPSection·SOP·Asset 을 읽기만 한다. 벡터 검색은 Neo4jVector 와 같은 필터 의미($like=CONTAINS, $eq)를
지키는 오프라인 검색기(HashEmbeddings, 파이썬 코사인)로 대신한다 — 공유 Neo4j 에 임베딩·인덱스를 쓰지 않기 위해서다.
"""
from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("HYDOPS_AGENT_MODE", "offline")

HERE = Path(__file__).resolve().parent
BASE = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
SKILL_DIR = BASE / "skills"


def _load(name: str):
    mod_name = f"lab_s05_{name}_{'solution' if BASE.name == 'solution' else 'student'}"
    spec = importlib.util.spec_from_file_location(mod_name, BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load("search_lab")


# ---- 오프라인 검색기 (Neo4jVector 필터 의미를 그대로 따른다) ------------------------------
def _matches(meta: dict, flt: dict) -> bool:
    for key, cond in (flt or {}).items():
        for op, val in cond.items():
            v = meta.get(key)
            if op == "$like" and not (isinstance(v, str) and str(val) in v):
                return False
            if op == "$eq" and v != val:
                return False
    return True


@pytest.fixture(scope="module")
def sections():
    from hydops.b4_ontology import graph

    rows = graph.run(
        "MATCH (x:SOPSection) RETURN x.id AS id, x.doc_id AS doc_id, x.version AS version, x.section_no AS section_no, "
        "x.heading AS heading, x.status AS status, x.asset_scope AS asset_scope, x.event_type AS event_type, x.text AS text ORDER BY x.id"
    )
    assert len(rows) >= 40, "SOPSection 이 적재돼 있어야 한다 (graph.seed_graph 는 강사가 준비)"
    return rows


@pytest.fixture(scope="module")
def retrieve(sections):
    from hydops.b6_sop.search import HashEmbeddings

    emb = HashEmbeddings()
    vecs = {s["id"]: emb.embed_query(s["text"]) for s in sections}

    def _retrieve(query: str, k: int, flt: dict):
        q = emb.embed_query(query)
        scored = []
        for s in sections:
            meta = {k2: s[k2] for k2 in ("id", "doc_id", "version", "section_no", "heading", "status", "asset_scope", "event_type")}
            if not _matches(meta, flt):
                continue
            cos = sum(a * b for a, b in zip(q, vecs[s["id"]]))
            scored.append((meta, s["text"], (cos + 1) / 2))
        scored.sort(key=lambda x: -x[2])
        return scored[:k]

    return _retrieve


# ---- 1. 필터 --------------------------------------------------------------------------------
def test_filter_has_pipe_boundary_and_active_status():
    assert L.build_filter("HYD-01") == {"asset_scope": {"$like": "|HYD-01|"}, "status": {"$eq": "active"}}
    assert L.build_filter("HYD-01", include_superseded=True) == {"asset_scope": {"$like": "|HYD-01|"}}
    assert not _matches({"asset_scope": "|HYD-011|", "status": "active"}, L.build_filter("HYD-01")), "HYD-01 필터가 HYD-011 에 걸리면 안 된다"
    assert not _matches({"asset_scope": "|HYD-01|", "status": "superseded"}, L.build_filter("HYD-01"))


# ---- 2. 그래프 확인 ---------------------------------------------------------------------------
def test_graph_confirmation_drops_other_event_type_and_unrelated_sop():
    fake = [
        ({"id": "SOP-SEN-001@v1#6", "doc_id": "SOP-SEN-001", "version": 1, "section_no": "6", "heading": "재점검 기준"}, "센서", 0.9),
        ({"id": "SOP-COOL-002@v1#4", "doc_id": "SOP-COOL-002", "version": 1, "section_no": "4", "heading": "허용 조치"}, "2호기", 0.85),
        ({"id": "SOP-COOL-001@v2#2", "doc_id": "SOP-COOL-001", "version": 2, "section_no": "2", "heading": "발동 조건"}, "1호기", 0.8),
        ({"id": "SOP-COOL-001@v2#2", "doc_id": "SOP-COOL-001", "version": 2, "section_no": "2", "heading": "발동 조건"}, "1호기", 0.8),
    ]
    hits = L.confirm_with_graph(fake, "HYD-01", "COOLING_ANOMALY", k=4)
    assert [(h["doc_id"], h["version"], h["section"]) for h in hits] == [("SOP-COOL-001", 2, "2")]


@pytest.mark.parametrize("asset_id", ["HYD-01", "HYD-02"])
def test_search_returns_only_applicable_active_cooling_sections(asset_id, retrieve):
    from hydops.b4_ontology import graph

    res = L.search_sop_lab(asset_id, "COOLING_ANOMALY", k=20, retrieve=retrieve)
    applicable = {(s["doc_id"], s["version"]) for s in graph.applicable_sops(asset_id, "COOLING_ANOMALY")}
    assert res["hits"], "적용 SOP 가 있는 설비는 절이 검색돼야 한다"
    assert all((h["doc_id"], h["version"]) in applicable for h in res["hits"]), res["hits"]
    assert len({(h["doc_id"], h["section"]) for h in res["hits"]}) == len(res["hits"]), "같은 절이 두 번 나오면 안 된다"


def test_superseded_only_when_asked(retrieve):
    active = L.search_sop_lab("HYD-01", "COOLING_ANOMALY", k=20, retrieve=retrieve)["hits"]
    assert all(not (h["doc_id"] == "SOP-COOL-001" and h["version"] == 1) for h in active)
    allv = L.search_sop_lab("HYD-01", "COOLING_ANOMALY", k=20, include_superseded=True, retrieve=retrieve)["hits"]
    assert any(h["doc_id"] == "SOP-COOL-001" and h["version"] == 1 for h in allv)


def test_new_asset_without_sop_has_no_hits(retrieve):
    assert L.search_sop_lab("HYD-03", "COOLING_ANOMALY", k=20, retrieve=retrieve)["hits"] == []


# ---- 3. 근거 검증 -----------------------------------------------------------------------------
def _trace(hits):
    return [{"tool": "search_sop", "result": {"hits": hits}}]


def test_fabricated_citation_is_held():
    from hydops.b7_agent.agent import Proposal

    trace = _trace([{"doc_id": "SOP-COOL-001", "version": 2, "section": "2"}, {"doc_id": "SOP-COOL-001", "version": 2, "section": "3"}])
    ok = Proposal(decision="PROPOSE", action_id="REDUCE_LOAD", value=0.8, citations=[{"doc_id": "SOP-COOL-001", "version": 2, "section": "2"}], rationale="r")
    assert L.verify_citations_lab(ok, trace)[0].decision == "PROPOSE"
    for bad in ({"doc_id": "SOP-COOL-001", "version": 1, "section": "2"}, {"doc_id": "SOP-COOL-001", "version": 2, "section": "4"}):
        p = Proposal(decision="PROPOSE", action_id="REDUCE_LOAD", value=0.8, citations=[bad], rationale="r")
        final, problems = L.verify_citations_lab(p, trace)
        assert final.decision == "HOLD" and final.citations == [] and problems, f"검색되지 않은 인용 {bad} 이 통과했다"
    empty = Proposal(decision="PROPOSE", action_id="REDUCE_LOAD", value=0.8, citations=[], rationale="r")
    assert L.verify_citations_lab(empty, trace)[0].decision == "HOLD", "인용 없는 제안은 보류한다"


# ---- 4. 오프라인 에이전트 ----------------------------------------------------------------------
def test_offline_agent_paths(retrieve):
    r1 = L.offline_proposal("HYD-01", "COOLING_ANOMALY", retrieve=retrieve)["final"]
    assert r1["decision"] == "PROPOSE" and r1["action_id"] == "REDUCE_LOAD" and r1["value"] == 0.8 and r1["citations"]
    r2 = L.offline_proposal("HYD-02", "COOLING_ANOMALY", retrieve=retrieve)["final"]
    assert r2["decision"] == "PROPOSE" and r2["action_id"] == "FAN_BOOST"
    assert all(c["doc_id"] != "SOP-COOL-001" for c in r2["citations"])
    r3 = L.offline_proposal("HYD-03", "COOLING_ANOMALY", retrieve=retrieve)["final"]
    assert r3["decision"] == "HOLD" and r3["citations"] == []
    r4 = L.offline_proposal("HYD-01", "COOLING_ANOMALY", sensor_state="SENSOR_FAULT", retrieve=retrieve)["final"]
    assert r4["decision"] == "SENSOR_CHECK" and r4["citations"] and all(c["doc_id"] == "SOP-SEN-001" for c in r4["citations"])


# ---- 5. SKILL.md -----------------------------------------------------------------------------
def _skill():
    text = (SKILL_DIR / "hydraulic-cooling-response" / "SKILL.md").read_text()
    _, fm, body = text.split("---", 2)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    sections = {}
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, flags=re.S | re.M):
        sections[m.group(1).strip()] = m.group(2)
    return yaml.safe_load(fm), sections


def test_skill_frontmatter_tools_are_proposal_only():
    meta, _ = _skill()
    assert meta["name"] == "hydraulic-cooling-response"
    assert set(meta["tools"]) == {"get_asset_context", "get_recent_window", "search_sop", "propose_action"}


def test_skill_order_sensor_first_then_context_search_propose():
    _, sec = _skill()
    order = sec["판단 순서"]
    pos = [order.find(t) for t in ("get_recent_window", "get_asset_context", "search_sop", "propose_action")]
    assert -1 not in pos and pos == sorted(pos), f"판단 순서 위치 {pos}"
    assert "execute_sim_action" not in order


def test_skill_citation_rules_do_not_hardcode_sections():
    _, sec = _skill()
    rules = sec["인용 규칙"]
    assert not re.search(r"§\s*\d", rules), "인용 규칙에 절 번호를 박아 넣으면 LLM 이 검색되지 않은 절을 인용한다"
    assert "hits" in rules or "검색 결과" in rules
    assert "인용하지 않는다" in rules, "Skill 문서 자체는 근거로 인용하지 않는다는 규칙이 필요하다"


def test_skill_stop_rules_hold_and_sensor_check():
    _, sec = _skill()
    stop = sec["중단 규칙"]
    assert "HOLD" in stop and "SENSOR_CHECK" in stop
    assert "REDUCE_LOAD" not in stop, "근거가 없을 때 특정 조치를 제안하라는 규칙이 남아 있다"


def test_skill_loads_into_system_prompt():
    from hydops.b7_agent.skill_loader import MAX_CHARS, build_system_prompt, load_skill

    sk = load_skill("hydraulic-cooling-response", SKILL_DIR)
    assert len(sk["body"]) < MAX_CHARS
    prompt = build_system_prompt(["hydraulic-cooling-response"], SKILL_DIR)
    assert "[할당된 스킬 가이드]" in prompt and "## 중단 규칙" in prompt
