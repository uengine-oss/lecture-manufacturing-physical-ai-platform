"""교육용 플랫폼 (Lab Platform) — 실라버스 아키텍처의 '후반부 플랫폼 연결' 열을 수업 환경에서 재현한다.

| 계층          | 교육용 모듈        | 실제 플랫폼 대응                         |
|---------------|--------------------|------------------------------------------|
| Data Sources  | /fabric            | Data Fabric 데이터소스                   |
| Ontology      | /studio            | Ontology Studio 클래스·관계·Behavior 발행 |
| Agents        | /agents            | Process GPT 업무 에이전트 · Ontologic 감시 |
| Orchestration | /process, /apps    | Process GPT 프로세스 · 아이나루 앱         |
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from labplatform import agents, apps, db, fabric, process, studio

BASE = Path(__file__).parent
# API 키는 강의 저장소에 복사하지 않고 플랫폼 .env 에서 읽는다 (hydops.config 와 같은 규칙)
for _p in (BASE.parent / ".env", Path(os.environ.get("HYDOPS_ENV_FILE", "/Users/uengine/uengine-platform/process-gpt/.env"))):
    if _p.exists():
        load_dotenv(_p, override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    (BASE / "data" / "apps").mkdir(parents=True, exist_ok=True)
    process.Engine().start()
    agents.WatchScheduler().start()
    yield


app = FastAPI(title="HydOps Lab Platform (교육용)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for r in (fabric.router, studio.router, agents.router, process.router, apps.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/")
def root():
    return RedirectResponse("/console/")


(BASE / "data" / "apps").mkdir(parents=True, exist_ok=True)
app.mount("/apps", StaticFiles(directory=BASE / "data" / "apps", html=True), name="published-apps")
app.mount("/console", StaticFiles(directory=BASE / "console", html=True), name="console")
