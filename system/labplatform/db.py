"""교육용 플랫폼 메타데이터 저장소 (PostgreSQL 스키마 labplatform).

실제 플랫폼은 여러 서비스에 흩어진 메타데이터를 쓰지만, 수업에서는 JSON 문서 한 테이블로 단순화한다.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DSN = os.environ.get("LAB_PG_DSN", "postgresql://hydops:hydops@localhost:55432/hydops")


def _dumps(o):
    return json.dumps(o, ensure_ascii=False, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x))


@contextmanager
def conn():
    with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as c:
        yield c


def init() -> None:
    with conn() as c:
        c.execute("CREATE SCHEMA IF NOT EXISTS labplatform")
        c.execute(
            """CREATE TABLE IF NOT EXISTS labplatform.doc (
                   kind TEXT NOT NULL, id TEXT NOT NULL, body JSONB NOT NULL,
                   created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                   PRIMARY KEY (kind, id))"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS labplatform.log (
                   id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL, message TEXT NOT NULL,
                   detail JSONB, at TIMESTAMPTZ NOT NULL DEFAULT now())"""
        )


def reset() -> None:
    with conn() as c:
        c.execute("DROP SCHEMA IF EXISTS labplatform CASCADE")
    init()


def put(kind: str, id: str, body: dict) -> dict:
    with conn() as c:
        c.execute(
            """INSERT INTO labplatform.doc (kind, id, body) VALUES (%s,%s,%s)
               ON CONFLICT (kind, id) DO UPDATE SET body=EXCLUDED.body, updated_at=now()""",
            (kind, id, Jsonb(body, dumps=_dumps)),
        )
    return body


def insert_new(kind: str, id: str, body: dict) -> bool:
    """이미 있으면 False (중복 방지 키로 쓴다)."""
    with conn() as c:
        r = c.execute(
            "INSERT INTO labplatform.doc (kind, id, body) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
            (kind, id, Jsonb(body, dumps=_dumps)),
        ).fetchone()
    return r is not None


def get(kind: str, id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT body FROM labplatform.doc WHERE kind=%s AND id=%s", (kind, id)).fetchone()
    return r["body"] if r else None


def list_(kind: str) -> list[dict]:
    with conn() as c:
        return [r["body"] for r in c.execute("SELECT body FROM labplatform.doc WHERE kind=%s ORDER BY created_at", (kind,)).fetchall()]


def delete(kind: str, id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM labplatform.doc WHERE kind=%s AND id=%s", (kind, id))


def log(kind: str, ref: str, message: str, detail: dict | None = None) -> None:
    with conn() as c:
        c.execute("INSERT INTO labplatform.log (kind, ref, message, detail) VALUES (%s,%s,%s,%s)", (kind, ref, message, Jsonb(detail, dumps=_dumps) if detail else None))


def logs(kind: str, ref: str | None = None, limit: int = 200) -> list[dict]:
    with conn() as c:
        if ref:
            return c.execute("SELECT * FROM labplatform.log WHERE kind=%s AND ref=%s ORDER BY id DESC LIMIT %s", (kind, ref, limit)).fetchall()
        return c.execute("SELECT * FROM labplatform.log WHERE kind=%s ORDER BY id DESC LIMIT %s", (kind, limit)).fetchall()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
