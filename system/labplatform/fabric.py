"""Data Fabric (교육용) — 데이터소스 등록·연결 확인·메타데이터 추출·읽기 전용 질의.

실제 플랫폼 대응: Data Fabric 데이터소스 (engine=postgres).
"""
from __future__ import annotations

import re

import psycopg
from fastapi import APIRouter, Body, HTTPException
from psycopg.rows import dict_row

from labplatform import db

router = APIRouter(prefix="/fabric", tags=["Data Fabric"])
ENGINES = {"postgres"}


def _dsn(p: dict) -> str:
    return f"postgresql://{p['user']}:{p['password']}@{p['host']}:{p.get('port', 5432)}/{p['database']}"


def _public(ds: dict) -> dict:
    d = {**ds, "parameters": {**ds["parameters"], "password": "******"}}
    return d


def query(name: str, sql: str, params: list | tuple | None = None, limit: int = 500) -> list[dict]:
    """읽기 전용 트랜잭션으로 질의한다. 쓰기 문장은 거부한다."""
    ds = db.get("datasource", name)
    if ds is None:
        raise HTTPException(404, f"datasource {name} not registered")
    if re.search(r"\b(insert|update|delete|drop|alter|create|truncate|grant)\b", sql, re.I):
        raise HTTPException(400, "Data Fabric 질의는 읽기 전용이다")
    with psycopg.connect(_dsn(ds["parameters"]), row_factory=dict_row) as c:
        c.execute("SET TRANSACTION READ ONLY")
        rows = c.execute(sql, params or ()).fetchmany(limit)
    return rows


@router.post("/datasources")
def register(body: dict = Body(...)):
    name, engine, params = body["name"], body.get("engine", "postgres"), body["parameters"]
    if engine not in ENGINES:
        raise HTTPException(400, f"engine must be one of {sorted(ENGINES)}")
    try:
        with psycopg.connect(_dsn(params), connect_timeout=5) as c:
            version = c.execute("select version()").fetchone()[0]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"연결 실패: {e}") from e
    ds = {"name": name, "engine": engine, "parameters": params, "description": body.get("description", ""), "server_version": version.split(",")[0], "registered_at": db.now(), "metadata": None}
    db.put("datasource", name, ds)
    db.log("fabric", name, "registered", {"server": ds["server_version"]})
    return _public(ds)


@router.get("/datasources")
def list_datasources():
    return [_public(d) for d in db.list_("datasource")]


@router.get("/datasources/{name}")
def get_datasource(name: str):
    ds = db.get("datasource", name)
    if not ds:
        raise HTTPException(404, "not found")
    return _public(ds)


@router.post("/datasources/{name}/extract-metadata")
def extract_metadata(name: str, body: dict = Body(default={})):
    schema = body.get("schema", "public")
    rows = query(
        name,
        """SELECT c.table_name, c.column_name, c.data_type, c.ordinal_position
           FROM information_schema.columns c JOIN information_schema.tables t
             ON t.table_schema=c.table_schema AND t.table_name=c.table_name AND t.table_type='BASE TABLE'
           WHERE c.table_schema=%s ORDER BY c.table_name, c.ordinal_position""",
        (schema,),
        limit=5000,
    )
    tables: dict = {}
    for r in rows:
        tables.setdefault(r["table_name"], []).append({"name": r["column_name"], "type": r["data_type"]})
    ds = db.get("datasource", name)
    ds["metadata"] = {"schema": schema, "tables": tables, "extracted_at": db.now()}
    db.put("datasource", name, ds)
    db.log("fabric", name, "metadata extracted", {"tables": len(tables)})
    return ds["metadata"]


@router.post("/datasources/{name}/query")
def run_query(name: str, body: dict = Body(...)):
    rows = query(name, body["sql"], body.get("params"), int(body.get("limit", 100)))
    return {"rows": rows, "count": len(rows)}
