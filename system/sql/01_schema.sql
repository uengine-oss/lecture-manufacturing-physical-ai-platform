-- B3 시계열 DB · B5 이벤트 · B8 조치 이력 (실라버스 '데이터 저장과 온톨로지 설계')
-- 수치 관측과 실행 이력은 PostgreSQL, 설비 관계와 SOP는 Neo4j 에 둔다.

CREATE TABLE IF NOT EXISTS run (
    run_id        TEXT PRIMARY KEY,
    source        TEXT NOT NULL CHECK (source IN ('uci_replay', 'simulator')),  -- 원본/합성 구분
    seed          INTEGER,
    scenario      TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    note          TEXT
);

CREATE TABLE IF NOT EXISTS observation (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES run(run_id),
    asset_id        TEXT NOT NULL,
    sensor_id       TEXT NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,      -- replay_ts (재생 시각, 실제 수집 시각 아님)
    elapsed_s       INTEGER,                   -- 사이클 내 경과 초 (위상)
    origin_cycle_id INTEGER,                   -- UCI 원본 사이클 번호 (합성은 NULL)
    raw_value       DOUBLE PRECISION,          -- 원시 값 (결측이면 NULL)
    value           DOUBLE PRECISION,          -- 정제 값 (품질 불량이면 NULL)
    unit            TEXT NOT NULL,
    quality_flag    TEXT NOT NULL DEFAULT 'OK',
    agg             JSONB,                     -- 1초 축약 통계 (min/max/n)
    is_synthetic    BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_obs_asset_sensor_ts ON observation (asset_id, sensor_id, ts DESC);
CREATE INDEX IF NOT EXISTS ix_obs_run ON observation (run_id);

CREATE TABLE IF NOT EXISTS event (
    event_id        TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES run(run_id),
    asset_id        TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('COOLING_ANOMALY', 'SENSOR_FAULT', 'PRODUCT_QUALITY')),
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    rule_version    TEXT NOT NULL,
    evidence        JSONB NOT NULL,            -- 근거 요약
    status          TEXT NOT NULL DEFAULT 'DETECTED',
    status_reason   TEXT,
    proposal        JSONB,                     -- B7 제안 (근거 참조 포함)
    process_ref     JSONB,                     -- 플랫폼 프로세스 인스턴스 대응 (event_id ↔ proc_inst_id)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 같은 설비·같은 유형의 열린 사건은 하나만 (이벤트 중복 억제)
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_open
    ON event (asset_id, event_type)
    WHERE status NOT IN ('CLOSED', 'ESCALATED', 'REJECTED', 'HOLD_NO_EVIDENCE', 'SENSOR_CHECK', 'RUN_ENDED');

CREATE TABLE IF NOT EXISTS event_history (
    id          BIGSERIAL PRIMARY KEY,
    event_id    TEXT NOT NULL REFERENCES event(event_id),
    from_status TEXT,
    to_status   TEXT NOT NULL,
    actor       TEXT NOT NULL,                 -- detector / agent / human:<name> / executor / verifier
    detail      JSONB,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval (
    approval_id     TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES event(event_id),
    approver        TEXT NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    action_id       TEXT NOT NULL,
    approved_value  DOUBLE PRECISION,
    comment         TEXT,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_log (
    action_log_id   TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES event(event_id),
    approval_id     TEXT REFERENCES approval(approval_id),
    action_id       TEXT NOT NULL,
    requested_value DOUBLE PRECISION,
    idempotency_key TEXT NOT NULL UNIQUE,      -- 중복 실행 방지 키 (event_id:action_id:attempt)
    command_status  TEXT NOT NULL,             -- SUCCEEDED / FAILED / REJECTED_POLICY
    command_detail  JSONB,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sim_ts          TIMESTAMPTZ                -- 조치가 적용된 시뮬레이터 시각
);

CREATE TABLE IF NOT EXISTS verification (
    verification_id TEXT PRIMARY KEY,
    action_log_id   TEXT NOT NULL REFERENCES action_log(action_log_id),
    event_id        TEXT NOT NULL REFERENCES event(event_id),
    window_start    TIMESTAMPTZ NOT NULL,      -- 조치 이후 관측만 참조
    window_end      TIMESTAMPTZ NOT NULL,
    outcome         TEXT NOT NULL CHECK (outcome IN ('RECOVERED', 'NOT_IMPROVED', 'INSUFFICIENT_DATA')),
    metrics         JSONB NOT NULL,
    verified_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 합성 제품 검사값 (제품 품질 확장: 설비 이상과 별도 기록)
CREATE TABLE IF NOT EXISTS inspection (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run(run_id),
    lot_id      TEXT NOT NULL,
    asset_id    TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    measure     TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    lsl         DOUBLE PRECISION NOT NULL,
    usl         DOUBLE PRECISION NOT NULL,
    unit        TEXT NOT NULL,
    is_synthetic BOOLEAN NOT NULL DEFAULT true
);
