"""강사 준비 스크립트 — 교육용 플랫폼에 수업 전 연결을 만든다.

단계를 골라 실행할 수 있다. 학생 실습 단계(발행·할당·게시)는 --upto 로 멈춰 두고 수업에서 직접 한다.
  python scripts/bootstrap_platform.py --upto datasource   # 6회차 시작 상태
  python scripts/bootstrap_platform.py --upto ontology     # 매핑 가져오기까지 (발행은 학생)
  python scripts/bootstrap_platform.py --all               # 전체 (강사 리허설)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
P = "http://localhost:8910"
HYDOPS = "http://localhost:8800"
T = ROOT / "labplatform" / "templates"
STAGES = ["datasource", "ontology", "publish", "skill", "mcp", "agent", "process", "watch", "app"]


def ok(r: httpx.Response):
    if r.status_code >= 400:
        raise SystemExit(f"{r.request.method} {r.request.url} → {r.status_code} {r.text[:500]}")
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upto", choices=STAGES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--enable-watch", action="store_true")
    a = ap.parse_args()
    stages = STAGES if a.all else STAGES[: STAGES.index(a.upto) + 1]
    c = httpx.Client(timeout=60)

    if "datasource" in stages:
        # 스코프된 읽기 전용 계정: 다른 스키마·쓰기 권한이 카탈로그에 섞이지 않게 한다
        with psycopg.connect("postgresql://hydops:hydops@localhost:55432/hydops", autocommit=True) as pg:
            pg.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='lab_reader') THEN CREATE ROLE lab_reader LOGIN PASSWORD 'lab_reader'; END IF; END $$")
            pg.execute("GRANT USAGE ON SCHEMA public TO lab_reader")
            pg.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO lab_reader")
            pg.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO lab_reader")
        print("datasource", ok(c.post(f"{P}/fabric/datasources", json={"name": "hydops_edu", "engine": "postgres", "description": "교육용 유압설비 운영 DB (읽기 전용 계정)", "parameters": {"host": "localhost", "port": 55432, "database": "hydops", "user": "lab_reader", "password": "lab_reader"}}))["server_version"])
        md = ok(c.post(f"{P}/fabric/datasources/hydops_edu/extract-metadata", json={}))
        print("  tables", sorted(md["tables"]))
    if "ontology" in stages:
        print("ontology import", ok(c.post(f"{P}/studio/schemas/import", json=json.loads((T / "ontology_hydraulic.json").read_text()))))
    if "publish" in stages:
        print("publish", ok(c.post(f"{P}/studio/schemas/HydraulicOps/publish")))
    if "skill" in stages:
        print("skill", ok(c.post(f"{P}/agents/skills", json={"files": {"SKILL.md": (ROOT / "skills" / "hydraulic-cooling-response" / "SKILL.md").read_text()}})))
    if "mcp" in stages:
        print("mcp", ok(c.post(f"{P}/agents/mcp-servers", json={"name": "hydops", "type": "http", "url": f"{HYDOPS}/mcp/"})))
        print("  tools", [t["name"] for t in ok(c.get(f"{P}/agents/mcp-servers/hydops/tools"))])
    if "agent" in stages:
        print("agent", ok(c.post(f"{P}/agents", json=json.loads((T / "agent_ops.json").read_text())))["agent_id"])
    if "process" in stages:
        print("process", ok(c.post(f"{P}/process/definitions", json=json.loads((T / "process_cooling_response.json").read_text()))))
    if "watch" in stages:
        w = json.loads((T / "watch_events.json").read_text())
        w["enabled"] = a.enable_watch
        print("watch", ok(c.post(f"{P}/agents/watch", json=w))["watch_id"], "enabled" if w["enabled"] else "disabled")
    if "app" in stages:
        app = ok(c.post(f"{P}/apps", json={"name": "hydops-ops", "template": "ops-console", "config": {"hydops_api": HYDOPS, "platform_api": P, "schema_name": "HydraulicOps", "process_def_id": "cooling_response"}}))
        print("app", app["url"], app["status"])


if __name__ == "__main__":
    main()
