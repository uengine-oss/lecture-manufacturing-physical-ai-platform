"""통합반 2회 · 품질 플래그와 시계열 DB — 빈칸(____)을 채우는 실습 파일.

흐름: 오류 주입본(B1) → 품질 검사(B2) → PostgreSQL 적재(B3) → 최근 60초·구간 조회 → 내 행 지우기

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python ../labs/integrated/S02/quality_lab.py
- 빈칸은 [빈칸 1]~[빈칸 3] 세 곳이다. 나머지 코드는 제공 코드이므로 고치지 않는다.
- DB 에는 run_id 가 LAB-S02- 로 시작하는 내 행만 쓰고, 끝나면 그 행만 지운다.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone

from hydops.b1_data import uci
from hydops.b2_quality.checks import SensorQualityChecker, classify_window, window_quality
from hydops.b3_tsdb import store
from hydops.config import QualityRules

____ = None  # 빈칸 표시

ASSET_ID = "HYD-01"
CYCLE_ID = 1500  # 오류 주입본을 만들 UCI 원본 사이클
# 재생 시각: 임의로 정한 과거 시각. 실제 수집 시각이 아니다.
# (운영 중인 시뮬레이터 관측보다 앞선 시각이라 '설비의 최근 값' 조회에 섞이지 않는다)
REPLAY_START = datetime(2026, 1, 25, 9, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# [빈칸 1] 품질 기준 — 시스템 기준(hydops/config.py 의 QualityRules)과 같은 값을 넣는다
# ---------------------------------------------------------------------------
RULES = QualityRules(
    gap_hold_s=____,  # 몇 초 이상 연속으로 값이 없으면 GAP(판정 보류)인가
    stuck_run=____,  # 같은 값이 몇 번째 반복될 때부터 STUCK(고착)인가
    spike_delta={"TS1": ____, "PS1": 60.0, "FS1": 6.0},  # 1초 사이 온도(TS1)가 몇 °C 넘게 뛰면 SPIKE 인가
)

# ---------------------------------------------------------------------------
# [빈칸 2] 최근 60초 조회 — 품질 플래그와 원본 사이클 번호를 함께 꺼낸다
# ---------------------------------------------------------------------------
LAST_60S_SQL = """
SELECT sensor_id, ts, elapsed_s, ____, raw_value, value, unit, ____
FROM observation
WHERE run_id = %(run_id)s
  AND asset_id = %(asset_id)s
  AND sensor_id = %(sensor_id)s
  AND ts > (SELECT max(ts) FROM observation
            WHERE run_id = %(run_id)s AND asset_id = %(asset_id)s) - interval '____ seconds'
ORDER BY ts
"""

# ---------------------------------------------------------------------------
# [빈칸 3] 조회 구간 바꾸기 — 사이클 내 경과 초(elapsed_s) 범위 (처음, 끝) 둘 다 포함
# ---------------------------------------------------------------------------
NORMAL_RANGE = (____, ____)  # classify_window 결과가 VALID 인 구간
HOLD_RANGE = (____, ____)  # classify_window 결과가 SENSOR_FAULT(판정 보류)인 구간

RANGE_SQL = """
SELECT sensor_id, ts, elapsed_s, origin_cycle_id, raw_value, value, unit, quality_flag
FROM observation
WHERE run_id = %(run_id)s AND asset_id = %(asset_id)s AND sensor_id = %(sensor_id)s
  AND elapsed_s BETWEEN %(from_s)s AND %(to_s)s
ORDER BY ts
"""


# ======================= 아래는 제공 코드 (고치지 않는다) =======================
def make_injected_rows() -> list[dict]:
    """사이클 #1500 을 공통 관측 레코드로 바꾸고 TS1 에 결측·급등·고착을 섞는다."""
    ds = uci.load_reduced()
    return uci.inject_sensor_errors(uci.cycle_observations(ds, CYCLE_ID, ASSET_ID, REPLAY_START))


def check_rows(rows: list[dict], rules: QualityRules = RULES) -> list[dict]:
    return SensorQualityChecker(rules).check_many(rows)


def flag_counts(checked: list[dict], sensor_id: str = "TS1") -> dict:
    return dict(Counter(r["quality_flag"] for r in checked if r["sensor_id"] == sensor_id))


def new_run_id() -> str:
    return f"LAB-S02-{uuid.uuid4().hex[:8]}"


def load_to_db(run_id: str, checked: list[dict]) -> int:
    assert run_id.startswith("LAB-"), "실습 run_id 는 LAB- 로 시작해야 한다"
    store.create_run("uci_replay", "lab-s02-injected", note=f"통합반 S02 오류 주입본 사이클 #{CYCLE_ID}", run_id=run_id)
    return store.insert_observations(run_id, checked)


def last_60s(run_id: str, sensor_id: str = "TS1") -> list[dict]:
    with store.connect() as c:
        return c.execute(LAST_60S_SQL, {"run_id": run_id, "asset_id": ASSET_ID, "sensor_id": sensor_id}).fetchall()


def range_rows(run_id: str, rng: tuple, sensor_id: str = "TS1") -> list[dict]:
    with store.connect() as c:
        return c.execute(
            RANGE_SQL, {"run_id": run_id, "asset_id": ASSET_ID, "sensor_id": sensor_id, "from_s": rng[0], "to_s": rng[1]}
        ).fetchall()


def cleanup(run_id: str) -> int:
    """내 run_id 의 행만 지운다 (observation → run 순서). 남은 관측 수를 돌려준다."""
    assert run_id.startswith("LAB-")
    with store.connect() as c:
        c.execute("DELETE FROM observation WHERE run_id = %s", (run_id,))
        c.execute("DELETE FROM run WHERE run_id = %s", (run_id,))
        return c.execute("SELECT count(*) AS n FROM observation WHERE run_id = %s", (run_id,)).fetchone()["n"]


def main() -> None:
    checked = check_rows(make_injected_rows())
    print("① TS1 플래그 개수:", flag_counts(checked))
    print("   PS1:", flag_counts(checked, "PS1"), " FS1:", flag_counts(checked, "FS1"))
    run_id = new_run_id()
    try:
        print("② 적재:", run_id, load_to_db(run_id, checked), "행")
        rows = last_60s(run_id)
        print("③ 최근 60초 TS1:", len(rows), "행 · 원본 사이클", sorted({r["origin_cycle_id"] for r in rows}))
        for r in rows:
            if r["quality_flag"] != "OK":
                print(f"   {r['elapsed_s']:2d}초  raw={r['raw_value']}  value={r['value']}  {r['quality_flag']}")
        print("   구간 요약:", window_quality(rows), "→", classify_window(rows, RULES))
        for name, rng in (("정상", NORMAL_RANGE), ("보류", HOLD_RANGE)):
            part = range_rows(run_id, rng)
            print(f"④ {name} 구간 {rng}:", window_quality(part)["flags"], "→", classify_window(part, RULES))
    finally:
        print("⑤ 정리: 남은 관측", cleanup(run_id), "행")


if __name__ == "__main__":
    main()
