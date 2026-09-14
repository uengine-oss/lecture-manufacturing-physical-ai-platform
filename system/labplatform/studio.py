"""Ontology Studio (교육용) — 클래스·관계·바인딩·Behavior 정의, 발행, 객체 조회, Golden Question.

원칙 (실라버스 '플랫폼 연결 준비'):
- Neo4j 에 적재한 노드가 자동으로 플랫폼 클래스가 되지 않는다. 클래스 매핑과 '발행'이 있어야 조회된다.
- 수치 데이터는 원천 DB 와 가상 연결(virtual)하고, 설비·문서 지식은 그래프(graph)에 둔다.
- 발행과 데이터 존재를 구분한다: 발행됐지만 행이 0개면 note 로 알려준다.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Body, HTTPException
from neo4j import GraphDatabase

from labplatform import db, fabric

router = APIRouter(prefix="/studio", tags=["Ontology Studio"])
_driver = GraphDatabase.driver(os.environ.get("LAB_NEO4J_URI", "bolt://localhost:57687"), auth=(os.environ.get("LAB_NEO4J_USER", "neo4j"), os.environ.get("LAB_NEO4J_PASSWORD", "hydops-lecture")))
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def cypher(q: str, **p) -> list[dict]:
    with _driver.session() as s:
        return [r.data() for r in s.run(q, **p)]


def _schema(name: str) -> dict:
    sc = db.get("ontology", name)
    if not sc:
        raise HTTPException(404, f"schema {name} not found")
    return sc


def _class(sc: dict, cname: str) -> dict:
    for c in sc["classes"]:
        if c["name"] == cname:
            return c
    raise HTTPException(404, f"class {cname} not in schema {sc['schema_name']}")


@router.get("/schemas")
def list_schemas():
    return [{"schema_name": s["schema_name"], "description": s.get("description"), "classes": len(s["classes"]), "relationships": len(s["relationships"]), "published_version": s.get("published_version"), "published_at": s.get("published_at"), "dirty": s.get("dirty", True)} for s in db.list_("ontology")]


@router.get("/schemas/{name}")
def get_schema(name: str):
    return _schema(name)


@router.post("/schemas/import")
def import_schema(body: dict = Body(...)):
    """제공 클래스 매핑 템플릿을 가져온다 (발행하지 않는다)."""
    body = {**body, "published_version": None, "published_at": None, "dirty": True}
    body.setdefault("behaviors", {})
    db.put("ontology", body["schema_name"], body)
    return list_schemas()


@router.put("/schemas/{name}/classes")
def upsert_class(name: str, body: dict = Body(...)):
    sc = _schema(name)
    sc["classes"] = [c for c in sc["classes"] if c["name"] != body["name"]] + [body]
    sc["dirty"] = True
    db.put("ontology", name, sc)
    return body


@router.put("/schemas/{name}/relationships")
def upsert_relationship(name: str, body: dict = Body(...)):
    sc = _schema(name)
    sc["relationships"] = [r for r in sc["relationships"] if r["name"] != body["name"]] + [body]
    sc["dirty"] = True
    db.put("ontology", name, sc)
    return body


@router.put("/schemas/{name}/classes/{cname}/binding")
def set_binding(name: str, cname: str, body: dict = Body(...)):
    sc = _schema(name)
    c = _class(sc, cname)
    c["binding"] = body
    sc["dirty"] = True
    db.put("ontology", name, sc)
    return c


@router.put("/schemas/{name}/classes/{cname}/behaviors/{bname}")
def set_behavior(name: str, cname: str, bname: str, body: dict = Body(...)):
    sc = _schema(name)
    _class(sc, cname)
    sc.setdefault("behaviors", {}).setdefault(cname, {})[bname] = body
    sc["dirty"] = True
    db.put("ontology", name, sc)
    return body


@router.get("/schemas/{name}/validate")
def validate(name: str):
    sc = _schema(name)
    problems, checks = [], []
    names = {c["name"] for c in sc["classes"]}
    for c in sc["classes"]:
        keys = [p for p in c["properties"] if p.get("key")]
        if len(keys) != 1:
            problems.append(f"{c['name']}: 키 속성이 정확히 하나여야 한다")
        b = c.get("binding") or {}
        if b.get("kind") == "virtual":
            ds = db.get("datasource", b.get("datasource", ""))
            meta = (ds or {}).get("metadata") or {}
            cols = {x["name"] for x in meta.get("tables", {}).get(b.get("table"), [])}
            if not ds:
                problems.append(f"{c['name']}: 데이터소스 {b.get('datasource')} 미등록")
            elif not cols:
                problems.append(f"{c['name']}: 테이블 {b.get('table')} 메타데이터 없음 (extract-metadata 필요)")
            else:
                missing = [m["column"] for m in b["column_map"] if m["column"] not in cols]
                if missing:
                    problems.append(f"{c['name']}: 없는 컬럼 {missing}")
            checks.append({"class": c["name"], "kind": "virtual", "table": b.get("table")})
        elif b.get("kind") == "graph":
            n = cypher(f"MATCH (n:`{b['label']}`) RETURN count(n) AS n")[0]["n"] if IDENT.match(b.get("label", "")) else 0
            checks.append({"class": c["name"], "kind": "graph", "label": b.get("label"), "nodes": n})
        else:
            problems.append(f"{c['name']}: 바인딩 없음")
    for r in sc["relationships"]:
        if r["from"] not in names or r["to"] not in names:
            problems.append(f"관계 {r['name']}: 클래스 없음 ({r['from']}→{r['to']})")
    return {"ok": not problems, "problems": problems, "bindings": checks}


@router.post("/schemas/{name}/publish")
def publish(name: str):
    v = validate(name)
    if not v["ok"]:
        raise HTTPException(422, {"error": "검증 실패 — 발행하지 않았다", **v})
    sc = _schema(name)
    version = (sc.get("published_version") or 0) + 1
    cypher("MATCH (m:_OntologyModel {name:$n})-[*0..2]->(x) DETACH DELETE x", n=name)
    cypher("MERGE (m:_OntologyModel {name:$n}) SET m.version=$v, m.published_at=datetime(), m.golden_questions=$gq", n=name, v=version, gq=[g["question"] for g in sc.get("golden_questions", [])])
    for c in sc["classes"]:
        b = c["binding"]
        cypher(
            """MATCH (m:_OntologyModel {name:$n})
               MERGE (m)-[:HAS_CLASS]->(k:_OntologyClass {model:$n, name:$c})
               SET k.description=$d, k.binding_kind=$kind, k.source=$src, k.key=$key
               WITH k UNWIND $props AS p MERGE (k)-[:HAS_PROPERTY]->(:_OntologyProperty {model:$n, class:$c, name:p.name, type:p.type})""",
            n=name, c=c["name"], d=c.get("description", ""), kind=b["kind"], src=b.get("label") or f"{b.get('datasource')}.{b.get('table')}",
            key=[p["name"] for p in c["properties"] if p.get("key")][0], props=c["properties"],
        )
    for r in sc["relationships"]:
        cypher(
            """MATCH (a:_OntologyClass {model:$n, name:$f}), (b:_OntologyClass {model:$n, name:$t})
               MERGE (a)-[x:_RELATES {name:$r}]->(b) SET x.via=$via""",
            n=name, f=r["from"], t=r["to"], r=r["name"], via=str(r.get("via")),
        )
    # 조회는 발행한 시점의 매핑으로 한다 — 발행 뒤 고친 매핑은 다시 발행해야 반영된다
    sc["published_snapshot"] = {k: sc.get(k) for k in ("classes", "relationships", "behaviors", "golden_questions")}
    sc.update(published_version=version, published_at=db.now(), dirty=False)
    db.put("ontology", name, sc)
    db.log("studio", name, f"published v{version}", {"classes": len(sc["classes"]), "relationships": len(sc["relationships"])})
    return {"schema_name": name, "published_version": version, "classes": len(sc["classes"]), "relationships": len(sc["relationships"]), "bindings": v["bindings"]}


def _published(name: str) -> dict:
    sc = _schema(name)
    meta = cypher("MATCH (m:_OntologyModel {name:$n}) RETURN m.version AS v", n=name)
    if not sc.get("published_version") or not meta:
        raise HTTPException(409, f"schema {name} 이 발행되지 않았다 — 조회하려면 먼저 발행한다")
    snap = sc.get("published_snapshot") or {}
    return {**sc, **{k: v for k, v in snap.items() if v is not None}}


def fetch_objects(name: str, cname: str, filters: dict | None = None, limit: int = 50) -> dict:
    sc = _published(name)
    c = _class(sc, cname)
    b = c["binding"]
    filters = filters or {}
    props = {p["name"] for p in c["properties"]}
    for k in filters:
        if k not in props:
            raise HTTPException(400, f"{cname} 에 속성 {k} 가 없다")
    if b["kind"] == "graph":
        where = " AND ".join(f"n.`{k}` = ${k}" for k in filters) or "true"
        rows = cypher(f"MATCH (n:`{b['label']}`) WHERE {where} RETURN n {{.*}} AS o LIMIT $limit", limit=limit, **filters)
        objs = [{p["name"]: r["o"].get(p["name"]) for p in c["properties"]} for r in rows]
    else:
        cmap = {m["property"]: m["column"] for m in b["column_map"]}
        cols = ", ".join(f'"{cmap[p]}" AS "{p}"' for p in cmap)
        where = " AND ".join(f'"{cmap[k]}" = %s' for k in filters) or "true"
        base = " AND ".join(b.get("base_conditions", [])) or "true"
        order = f' ORDER BY "{b["order_by"]}" DESC' if b.get("order_by") else ""
        sql = f'SELECT {cols} FROM "{b["table"]}" WHERE {where} AND {base}{order} LIMIT {int(limit)}'
        objs = fabric.query(b["datasource"], sql, list(filters.values()))
    out = {"schema_name": name, "published_version": sc["published_version"], "class": cname, "binding_kind": b["kind"], "count": len(objs), "objects": objs}
    if not objs:
        out["note"] = "발행은 되었지만 조건에 맞는 데이터가 없다 (발행 ≠ 데이터 존재)"
    return out


@router.post("/schemas/{name}/objects/{cname}/fetch")
def fetch(name: str, cname: str, body: dict = Body(default={})):
    return fetch_objects(name, cname, body.get("filters"), int(body.get("limit", 50)))


@router.get("/schemas/{name}/objects/{cname}/{key}/related/{rel}")
def related(name: str, cname: str, key: str, rel: str, limit: int = 50):
    sc = _published(name)
    r = next((x for x in sc["relationships"] if x["name"] == rel and x["from"] == cname), None)
    if not r:
        raise HTTPException(404, f"relationship {rel} from {cname} not defined")
    src, dst = _class(sc, cname), _class(sc, r["to"])
    skey = [p["name"] for p in src["properties"] if p.get("key")][0]
    via = r["via"]
    if via["kind"] == "graph":
        rows = cypher(
            f"MATCH (a:`{src['binding']['label']}` {{`{skey}`: $key}}){'-' if via.get('direction', 'out') == 'out' else '<-'}[:`{via['rel_type']}`]{'->' if via.get('direction', 'out') == 'out' else '-'}(b:`{dst['binding']['label']}`) "
            f"WHERE {' AND '.join(f'b.`{k}` = ' + repr(v) for k, v in via.get('where', {}).items()) or 'true'} RETURN b {{.*}} AS o LIMIT $limit",
            key=key, limit=limit,
        )
        objs = [{p["name"]: x["o"].get(p["name"]) for p in dst["properties"]} for x in rows]
        out = {"from": f"{cname}:{key}", "relationship": rel, "to": r["to"], "count": len(objs), "objects": objs}
        if not objs:
            out["note"] = "발행은 되었지만 이 관계로 연결된 객체가 없다 (발행 ≠ 데이터 존재)"
        return out
    # join: 대상 클래스의 속성 == 출발 객체의 속성 (가상 연결)
    src_obj = fetch_objects(name, cname, {skey: key}, 1)["objects"]
    if not src_obj:
        raise HTTPException(404, f"{cname} {key} not found")
    res = fetch_objects(name, r["to"], {via["to_property"]: src_obj[0][via["from_property"]]}, limit)
    return {"from": f"{cname}:{key}", "relationship": rel, "to": r["to"], "count": res["count"], "objects": res["objects"], "note": res.get("note")}


@router.post("/schemas/{name}/objects/{cname}/behaviors/{bname}/invoke")
def invoke_behavior(name: str, cname: str, bname: str, body: dict = Body(default={})):
    sc = _published(name)
    beh = (sc.get("behaviors", {}).get(cname) or {}).get(bname)
    if not beh:
        raise HTTPException(404, f"behavior {cname}.{bname} not defined")
    args = body.get("arguments", {})
    missing = [p for p in beh["parameters"] if p not in args]
    if missing:
        raise HTTPException(400, f"missing arguments {missing}")
    rows = fabric.query(beh["datasource"], beh["sql_template"], [args[p] for p in beh["parameters"]], int(body.get("limit", beh.get("max_rows", 100))))
    return {"behavior": f"{cname}.{bname}", "arguments": args, "count": len(rows), "rows": rows}


@router.post("/schemas/{name}/golden")
def run_golden(name: str, body: dict = Body(default={})):
    """Golden Question 검증: 템플릿에 적힌 조회 단계를 실제로 실행하고 결과가 비지 않는지 확인한다."""
    sc = _published(name)
    params = body.get("params", {})
    results = []
    for g in sc.get("golden_questions", []):
        steps = []
        ok = True
        for st in g["steps"]:
            args = {k: (params.get(v[1:]) if isinstance(v, str) and v.startswith("$") else v) for k, v in st.get("args", {}).items()}
            try:
                if st["op"] == "fetch":
                    r = fetch_objects(name, st["class"], args, st.get("limit", 20))
                elif st["op"] == "related":
                    r = related(name, st["class"], args["key"], st["relationship"])
                elif st["op"] == "related_chain":
                    # 관계를 차례로 따라간다: 예) Asset -GOVERNED_BY-> SOP -ALLOWS-> Action
                    frontier, cls = [args["key"]], st["class"]
                    for rel in st["path"]:
                        rdef = next(x for x in sc["relationships"] if x["name"] == rel and x["from"] == cls)
                        nxt_cls = rdef["to"]
                        nkey = [p["name"] for p in _class(sc, nxt_cls)["properties"] if p.get("key")][0]
                        objs = []
                        for k in frontier:
                            objs += related(name, cls, k, rel)["objects"]
                        if st.get("where"):
                            objs = [o for o in objs if all(o.get(a) == b for a, b in st["where"].get(nxt_cls, {}).items())]
                        frontier, cls = list(dict.fromkeys(o[nkey] for o in objs)), nxt_cls
                    r = {"count": len(objs), "objects": objs}
                else:
                    r = invoke_behavior(name, st["class"], st["behavior"], {"arguments": args})
                n = r.get("count", 0)
                steps.append({"step": st.get("label", st["op"]), "count": n, "sample": (r.get("objects") or r.get("rows") or [])[:3]})
                ok = ok and n > 0
            except HTTPException as e:
                steps.append({"step": st.get("label", st["op"]), "error": e.detail})
                ok = False
        results.append({"question": g["question"], "answered": ok, "steps": steps})
    return {"schema_name": name, "published_version": sc["published_version"], "results": results}
