import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 테스트는 공유 DB 가 아니라 별도 데이터베이스(hydops_test)에서 돈다 — 수업·시연 기록을 지우지 않는다.
os.environ.setdefault("HYDOPS_PG_DSN", "postgresql://hydops:hydops@localhost:55432/hydops_test")
import psycopg  # noqa: E402

with psycopg.connect("postgresql://hydops:hydops@localhost:55432/hydops", autocommit=True) as _c:
    if not _c.execute("SELECT 1 FROM pg_database WHERE datname='hydops_test'").fetchone():
        _c.execute("CREATE DATABASE hydops_test")

from hydops.b3_tsdb import store  # noqa: E402
from hydops.b4_ontology import graph  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded():
    store.init_schema()
    graph.seed_graph()
    from hydops.b6_sop import search

    search.index_sections()
    yield


@pytest.fixture()
def clean():
    with store.connect() as c:
        ids = [r["event_id"] for r in c.execute("SELECT event_id FROM event").fetchall()]
        c.execute("TRUNCATE verification, action_log, approval, event_history, event, inspection CASCADE")
        for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            c.execute(f"DO $$ BEGIN IF to_regclass('{t}') IS NOT NULL THEN EXECUTE 'TRUNCATE {t}'; END IF; END $$")
    graph.run("MATCH (e:Event) WHERE e.event_id IN $ids DETACH DELETE e", ids=ids)  # 테스트가 만든 사건 참조만 지운다
    yield


@pytest.fixture()
def plant(clean):
    from hydops.b8_action.workflow import Orchestrator
    from hydops.runtime import PlantRuntime

    mode = os.environ.get("HYDOPS_TEST_AGENT_MODE", "offline")
    rt = PlantRuntime(assets=("HYD-01", "HYD-02", "HYD-03"), seed=42, scenario="pytest")
    orc = Orchestrator(rt, agent_mode=mode)
    yield rt, orc
    orc.close()
