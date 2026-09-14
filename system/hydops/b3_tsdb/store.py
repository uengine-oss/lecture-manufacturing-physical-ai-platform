"""B3 · PostgreSQL 저장소. 관측·사건·승인·조치·재측정을 기록하고 조회한다."""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from hydops.config import ROOT, SETTINGS


def _json(v: Any):
    return Jsonb(v, dumps=lambda o: json.dumps(o, default=str, ensure_ascii=False)) if v is not None else None


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(SETTINGS.pg_dsn, row_factory=dict_row, autocommit=True) as conn:
        yield conn


def init_schema(reset: bool = False) -> None:
    sql = (ROOT / "sql" / "01_schema.sql").read_text()
    with connect() as c:
        if reset:
            c.execute(
                "DROP TABLE IF EXISTS verification, action_log, approval, event_history, event, inspection, observation, run CASCADE"
            )
        c.execute(sql)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---- run / observation -------------------------------------------------------
def create_run(source: str, scenario: str, seed: int | None = None, note: str | None = None, run_id: str | None = None) -> str:
    run_id = run_id or new_id("RUN")
    with connect() as c:
        c.execute(
            "INSERT INTO run (run_id, source, seed, scenario, note) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO NOTHING",
            (run_id, source, seed, scenario, note),
        )
    return run_id


def insert_observations(run_id: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with connect() as c, c.cursor() as cur:
        with cur.copy(
            "COPY observation (run_id, asset_id, sensor_id, ts, elapsed_s, origin_cycle_id, raw_value, value, unit, quality_flag, agg, is_synthetic) FROM STDIN"
        ) as cp:
            for r in rows:
                cp.write_row(
                    (
                        run_id,
                        r["asset_id"],
                        r["sensor_id"],
                        r["ts"],
                        r.get("elapsed_s"),
                        r.get("origin_cycle_id"),
                        r.get("raw_value"),
                        r.get("value"),
                        r["unit"],
                        r.get("quality_flag", "OK"),
                        json.dumps(r["agg"]) if r.get("agg") else None,
                        r.get("is_synthetic", False),
                    )
                )
    return len(rows)


def recent_window(asset_id: str, seconds: int = 60, sensor_id: str | None = None, run_id: str | None = None, until: datetime | None = None) -> list[dict]:
    """설비별 최근 구간 SELECT. 기준 시각은 해당 설비의 마지막 관측 시각(재생 시각)이다."""
    with connect() as c:
        if until is None:
            q = "SELECT max(ts) AS t FROM observation WHERE asset_id=%s" + (" AND run_id=%s" if run_id else "")
            until = c.execute(q, (asset_id, run_id) if run_id else (asset_id,)).fetchone()["t"]
            if until is None:
                return []
        params: list[Any] = [asset_id, until - timedelta(seconds=seconds), until]
        q = """SELECT run_id, asset_id, sensor_id, ts, elapsed_s, origin_cycle_id, raw_value, value, unit, quality_flag, agg, is_synthetic
               FROM observation WHERE asset_id=%s AND ts > %s AND ts <= %s"""
        if sensor_id:
            q += " AND sensor_id=%s"
            params.append(sensor_id)
        if run_id:
            q += " AND run_id=%s"
            params.append(run_id)
        return c.execute(q + " ORDER BY ts, sensor_id", params).fetchall()


def observations_between(asset_id: str, sensor_id: str, start: datetime, end: datetime, run_id: str | None = None) -> list[dict]:
    with connect() as c:
        q = "SELECT * FROM observation WHERE asset_id=%s AND sensor_id=%s AND ts > %s AND ts <= %s"
        params: list[Any] = [asset_id, sensor_id, start, end]
        if run_id:
            q += " AND run_id=%s"
            params.append(run_id)
        return c.execute(q + " ORDER BY ts", params).fetchall()


# ---- event ------------------------------------------------------------------
def open_event(asset_id: str, event_type: str) -> dict | None:
    with connect() as c:
        return c.execute(
            """SELECT * FROM event WHERE asset_id=%s AND event_type=%s
               AND status NOT IN ('CLOSED','ESCALATED','REJECTED','HOLD_NO_EVIDENCE','SENSOR_CHECK','RUN_ENDED')""",
            (asset_id, event_type),
        ).fetchone()


def create_event(run_id: str, asset_id: str, event_type: str, window_start, window_end, rule_version: str, evidence: dict, status: str = "DETECTED") -> tuple[dict, bool]:
    """사건을 만든다. 같은 설비·유형의 열린 사건이 있으면 새로 만들지 않는다 (중복 억제)."""
    existing = open_event(asset_id, event_type)
    if existing:
        return existing, False
    event_id = f"EVT-{window_start:%Y%m%d-%H%M%S}-{asset_id}-{uuid.uuid4().hex[:4]}"
    with connect() as c:
        try:
            row = c.execute(
                """INSERT INTO event (event_id, run_id, asset_id, event_type, window_start, window_end, rule_version, evidence, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (event_id, run_id, asset_id, event_type, window_start, window_end, rule_version, _json(evidence), status),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            return open_event(asset_id, event_type), False
        c.execute(
            "INSERT INTO event_history (event_id, from_status, to_status, actor, detail) VALUES (%s,NULL,%s,'detector',%s)",
            (event_id, status, _json(evidence)),
        )
    return row, True


def end_open_events_of_other_runs(run_id: str) -> int:
    """시뮬레이터를 초기화하면 이전 실행의 열린 사건을 RUN_ENDED 로 닫는다 (종결·회복으로 기록하지 않는다)."""
    with connect() as c:
        rows = c.execute(
            """SELECT event_id FROM event WHERE run_id <> %s
               AND status NOT IN ('CLOSED','ESCALATED','REJECTED','HOLD_NO_EVIDENCE','SENSOR_CHECK','RUN_ENDED')""",
            (run_id,),
        ).fetchall()
    for r in rows:
        transition(r["event_id"], "RUN_ENDED", "system", {"note": "시뮬레이터 초기화 — 실행 종료"}, reason="실행 종료로 미완결")
    return len(rows)


def get_event(event_id: str) -> dict | None:
    with connect() as c:
        return c.execute("SELECT * FROM event WHERE event_id=%s", (event_id,)).fetchone()


def list_events(limit: int = 50, asset_id: str | None = None, run_id: str | None = None) -> list[dict]:
    q, p = "SELECT * FROM event WHERE true", []
    if asset_id:
        q += " AND asset_id=%s"
        p.append(asset_id)
    if run_id:
        q += " AND run_id=%s"
        p.append(run_id)
    with connect() as c:
        return c.execute(q + " ORDER BY created_at DESC LIMIT %s", p + [limit]).fetchall()


def transition(event_id: str, to_status: str, actor: str, detail: dict | None = None, reason: str | None = None, **fields) -> dict:
    with connect() as c:
        cur = c.execute("SELECT status FROM event WHERE event_id=%s FOR UPDATE", (event_id,)).fetchone()
        sets, params = ["status=%s", "updated_at=now()"], [to_status]
        if reason is not None:
            sets.append("status_reason=%s")
            params.append(reason)
        for k, v in fields.items():
            sets.append(f"{k}=%s")
            params.append(_json(v))
        row = c.execute(f"UPDATE event SET {', '.join(sets)} WHERE event_id=%s RETURNING *", params + [event_id]).fetchone()
        c.execute(
            "INSERT INTO event_history (event_id, from_status, to_status, actor, detail) VALUES (%s,%s,%s,%s,%s)",
            (event_id, cur["status"] if cur else None, to_status, actor, _json(detail)),
        )
        return row


def event_history(event_id: str) -> list[dict]:
    with connect() as c:
        return c.execute("SELECT * FROM event_history WHERE event_id=%s ORDER BY id", (event_id,)).fetchall()


# ---- approval / action / verification ----------------------------------------
def record_approval(event_id: str, approver: str, decision: str, action_id: str, approved_value: float | None, comment: str | None = None) -> dict:
    with connect() as c:
        return c.execute(
            """INSERT INTO approval (approval_id, event_id, approver, decision, action_id, approved_value, comment)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (new_id("APR"), event_id, approver, decision, action_id, approved_value, comment),
        ).fetchone()


def get_approval(approval_id: str) -> dict | None:
    with connect() as c:
        return c.execute("SELECT * FROM approval WHERE approval_id=%s", (approval_id,)).fetchone()


def approvals_for(event_id: str) -> list[dict]:
    with connect() as c:
        return c.execute("SELECT * FROM approval WHERE event_id=%s ORDER BY decided_at", (event_id,)).fetchall()


def insert_action_log(event_id: str, approval_id: str | None, action_id: str, value: float | None, idem_key: str, status: str, detail: dict, sim_ts=None) -> tuple[dict, bool]:
    """중복 실행 방지: 같은 idempotency_key 가 이미 있으면 기존 기록을 돌려준다."""
    with connect() as c:
        row = c.execute(
            """INSERT INTO action_log (action_log_id, event_id, approval_id, action_id, requested_value, idempotency_key, command_status, command_detail, sim_ts)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING *""",
            (new_id("ACT"), event_id, approval_id, action_id, value, idem_key, status, _json(detail), sim_ts),
        ).fetchone()
        if row:
            return row, True
        return c.execute("SELECT * FROM action_log WHERE idempotency_key=%s", (idem_key,)).fetchone(), False


def find_action_log(idem_key: str) -> dict | None:
    with connect() as c:
        return c.execute("SELECT * FROM action_log WHERE idempotency_key=%s", (idem_key,)).fetchone()


def get_action_log(action_log_id: str) -> dict | None:
    with connect() as c:
        return c.execute("SELECT * FROM action_log WHERE action_log_id=%s", (action_log_id,)).fetchone()


def actions_for(event_id: str) -> list[dict]:
    with connect() as c:
        return c.execute("SELECT * FROM action_log WHERE event_id=%s ORDER BY executed_at", (event_id,)).fetchall()


def insert_verification(action_log_id: str, event_id: str, start, end, outcome: str, metrics: dict) -> dict:
    with connect() as c:
        return c.execute(
            """INSERT INTO verification (verification_id, action_log_id, event_id, window_start, window_end, outcome, metrics)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (new_id("VER"), action_log_id, event_id, start, end, outcome, _json(metrics)),
        ).fetchone()


def verifications_for(event_id: str) -> list[dict]:
    with connect() as c:
        return c.execute("SELECT * FROM verification WHERE event_id=%s ORDER BY verified_at", (event_id,)).fetchall()


def insert_inspections(run_id: str, rows: list[dict]) -> None:
    with connect() as c, c.cursor() as cur:
        cur.executemany(
            "INSERT INTO inspection (run_id, lot_id, asset_id, ts, measure, value, lsl, usl, unit) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(run_id, r["lot_id"], r["asset_id"], r["ts"], r["measure"], r["value"], r["lsl"], r["usl"], r["unit"]) for r in rows],
        )


def event_trace(event_id: str) -> dict:
    """B9 · 같은 event_id 로 감지·근거·승인·조치·재측정 기록을 모두 모은다."""
    return {
        "event": get_event(event_id),
        "history": event_history(event_id),
        "approvals": approvals_for(event_id),
        "actions": actions_for(event_id),
        "verifications": verifications_for(event_id),
    }
