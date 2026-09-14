"""B6 · SOP 절 검색 (Neo4jVector RAG).

SOP 검색은 학습이 아니라 실행 시 근거를 제공하는 RAG 다. 임베딩 모델은 추가 학습 없이 사용한다.
검색은 두 겹으로 거른다.
  1) 벡터 인덱스 메타데이터 필터: 적용 설비(asset_scope)·유효 상태(status='active')
  2) 그래프 확인: (SOP)-[:APPLIES_TO]->(Asset) 관계가 실제로 있는 절만 남긴다
"""
from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from hydops.b4_ontology import graph
from hydops.config import SETTINGS


class HashEmbeddings(Embeddings):
    """오프라인용 결정적 임베딩 (문자 2-gram 해시). API 키 없이 실습·테스트를 이어가기 위한 대체재."""

    dim = 384

    def _embed(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        t = re.sub(r"\s+", " ", text.lower())
        tokens = t.split(" ") + [t[i : i + 2] for i in range(len(t) - 1)]
        for tok in tokens:
            if not tok.strip():
                continue
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) % 2 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


def _embedding_backend():
    if SETTINGS.agent_mode == "llm":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=SETTINGS.embedding_model), "openai", 1536
    return HashEmbeddings(), "offline", HashEmbeddings.dim


@lru_cache(maxsize=1)
def vector_store():
    from langchain_neo4j import Neo4jVector

    emb, name, dim = _embedding_backend()
    return Neo4jVector(
        embedding=emb,
        url=SETTINGS.neo4j_uri,
        username=SETTINGS.neo4j_user,
        password=SETTINGS.neo4j_password,
        index_name=f"sop_section_{name}",
        node_label="SOPSection",
        text_node_property="text",
        embedding_node_property=f"embedding_{name}",
        embedding_dimension=dim,
    )


def index_sections() -> int:
    """SOPSection 노드에 임베딩을 넣고 벡터 인덱스를 만든다 (강사 제공 단계)."""
    store = vector_store()
    rows = graph.run("MATCH (x:SOPSection) RETURN x.id AS id, x.text AS text ORDER BY x.id")
    emb = store.embedding.embed_documents([r["text"] for r in rows])
    graph.run(
        f"UNWIND $rows AS row MATCH (x:SOPSection {{id: row.id}}) CALL db.create.setNodeVectorProperty(x, '{store.embedding_node_property}', row.emb)",
        rows=[{"id": r["id"], "emb": e} for r, e in zip(rows, emb)],
    )
    store.create_new_index() if not _index_exists(store.index_name) else None
    graph.run("CALL db.awaitIndexes(60)")
    return len(rows)


def _index_exists(name: str) -> bool:
    return bool(graph.run("SHOW INDEXES YIELD name WHERE name = $n RETURN name", n=name))


def search_sop(asset_id: str, event_type: str, query: str | None = None, k: int = 4, include_superseded: bool = False) -> dict:
    """search_sop 도구의 본체: 문서 ID·버전·절·근거 본문을 돌려준다."""
    query = query or {
        "COOLING_ANOMALY": "온도 60도 초과 지속 냉각 이상 발동 조건 허용 조치 승인 부하 감소 재점검",
        "SENSOR_FAULT": "센서 결측 고착 품질 플래그 센서 점검 설비 조치 보류",
    }.get(event_type, event_type)
    store = vector_store()
    index_name = getattr(store, "index_name", None)  # 실습에서 바꿔 끼운 저장소는 인덱스 이름이 없을 수 있다
    if index_name and not _index_exists(index_name):  # 오프라인 임베딩 등 아직 인덱스가 없는 백엔드면 한 번 만든다
        index_sections()
    flt: dict = {"asset_scope": {"$like": f"|{asset_id}|"}}
    if not include_superseded:
        flt["status"] = {"$eq": "active"}
    docs = store.similarity_search_with_score(query, k=k * 3, filter=flt)

    # 그래프 확인: 실제 APPLIES_TO 관계가 있고 사건 유형이 맞는 SOP 만 근거로 인정
    applicable = {(s["doc_id"], s["version"]) for s in graph.applicable_sops(asset_id, event_type)}
    if include_superseded:
        applicable |= {
            (r["doc_id"], r["version"])
            for r in graph.run(
                "MATCH (s:SOP)-[:APPLIES_TO]->(:Asset {asset_id:$a}) WHERE s.event_type=$t RETURN s.doc_id AS doc_id, s.version AS version",
                a=asset_id,
                t=event_type,
            )
        }
    hits, seen = [], set()
    for doc, score in docs:
        m = doc.metadata
        key = (m["doc_id"], m["version"])
        if key not in applicable or m["id"] in seen:
            continue
        seen.add(m["id"])
        hits.append(
            {
                "doc_id": m["doc_id"],
                "version": m["version"],
                "section": m["section_no"],
                "heading": m["heading"],
                "score": round(float(score), 4),
                "text": doc.page_content,
            }
        )
        if len(hits) >= k:
            break
    return {"asset_id": asset_id, "event_type": event_type, "query": query, "filter": flt, "hits": hits}
