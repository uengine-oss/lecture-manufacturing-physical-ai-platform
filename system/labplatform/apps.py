"""Apps (교육용) — 제공 Vue 화면을 게시하고 배포 로그를 남긴다.

실제 플랫폼 대응: 아이나루 앱 생성·게시. 분석·시뮬레이터 서버는 사전 운영하고, 학생은 화면만 게시한다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, HTTPException

from labplatform import db

router = APIRouter(prefix="/apps", tags=["Apps"])
BASE = Path(__file__).parent
TEMPLATES = BASE / "app_templates"
PUBLISHED = BASE / "data" / "apps"


@router.get("/templates")
def templates():
    return [p.name for p in TEMPLATES.iterdir() if p.is_dir()]


@router.post("")
def publish(body: dict = Body(...)):
    name, tpl, cfg = body["name"], body.get("template", "ops-console"), body.get("config", {})
    if not name.replace("-", "").isalnum():
        raise HTTPException(400, "앱 이름은 영문·숫자·하이픈만")
    src = TEMPLATES / tpl
    if not src.exists():
        raise HTTPException(404, f"template {tpl} not found")
    dst = PUBLISHED / name
    steps = []

    def step(msg, **d):
        steps.append({"at": db.now(), "message": msg, **d})
        db.log("apps", name, msg, d or None)

    step("검증: 템플릿과 바인딩 설정 확인", template=tpl, bindings=list(cfg))
    required = ["hydops_api", "platform_api", "schema_name", "process_def_id"]
    missing = [k for k in required if k not in cfg]
    if missing:
        step("실패: 바인딩 누락", missing=missing)
        raise HTTPException(422, {"error": "바인딩 누락", "missing": missing, "steps": steps})
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    (dst / "config.js").write_text("window.APP_CONFIG = " + json.dumps({**cfg, "app_name": name}, ensure_ascii=False, indent=2) + ";\n")
    step("번들: 정적 파일 복사와 config.js 생성", files=sorted(p.name for p in dst.iterdir()))
    health = {}
    for k in ("hydops_api", "platform_api"):
        try:
            r = httpx.get(cfg[k].rstrip("/") + ("/api/state" if k == "hydops_api" else "/health"), timeout=5)
            health[k] = r.status_code
        except Exception as e:  # noqa: BLE001
            health[k] = repr(e)
    step("상태 확인: 바인딩된 서버 응답", **health)
    app = {"name": name, "template": tpl, "config": cfg, "url": f"/apps/{name}/", "status": "PUBLISHED" if all(v == 200 for v in health.values()) else "PUBLISHED_WITH_WARNINGS", "published_at": db.now(), "steps": steps}
    db.put("app", name, app)
    step(f"게시 완료: {app['url']}", status=app["status"])
    return app


@router.get("")
def list_apps():
    return db.list_("app")


@router.get("/{name}/logs")
def logs(name: str):
    return db.logs("apps", name)
