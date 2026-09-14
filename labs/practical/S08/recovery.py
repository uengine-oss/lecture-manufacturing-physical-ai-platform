"""S08 · 조치 후 재측정 판정 (학생 시작본 — 동작하지만 판정 조건 세 곳이 틀렸다).

원본: lecture/system/hydops/b8_action/executor.py 의 verify_window · verify_recovery.
원본은 PostgreSQL 의 observation 을 읽고 verification 을 기록한다. 수업용 복사본은 같은 판정을
메모리의 관측 행(시뮬레이터 → 품질 검사 결과)에 적용하고 기록은 하지 않는다.

rows   : SensorQualityChecker 를 거친 관측 행 목록 (asset_id, sensor_id, ts, value, quality_flag …)
action : 실행 기록 한 건 {"sim_ts": 조치 시각(시뮬레이터 시각), "command_status": "SUCCEEDED" | "FAILED"}
"""
from __future__ import annotations

from datetime import timedelta

from hydops.b2_quality.checks import OK
from hydops.config import TH, Thresholds


def verify_window(action: dict, th: Thresholds = TH, window_index: int = 0):
    """조치 30초 후부터 60초 창. 데이터 부족이면 window_index+1 로 다음 창을 잰다."""
    start = action["sim_ts"] + timedelta(seconds=th.verify_wait_s + window_index * th.verify_window_s)
    return start, start + timedelta(seconds=th.verify_window_s)


def judge_recovery(rows: list[dict], action: dict, th: Thresholds = TH, window_index: int = 0, sensor_id: str = "TS1") -> dict:
    """조치 이후 관측만 보고 RECOVERED / NOT_IMPROVED / INSUFFICIENT_DATA 를 판정한다."""
    start, end = verify_window(action, th, window_index)
    # TODO(학생) 1: 창의 끝만 자르고 시작을 자르지 않는다 — 조치 전(냉각 이상 주입 전) 관측까지 섞인다.
    win = sorted((r for r in rows if r["sensor_id"] == sensor_id and r["ts"] <= end), key=lambda r: r["ts"])
    # TODO(학생) 2: 결측 행을 먼저 지운 뒤 비율을 계산한다 — 유효 비율이 항상 100% 가 된다.
    win = [r for r in win if r["value"] is not None]
    valid = [r for r in win if r["quality_flag"] == OK and r["value"] is not None]
    ratio = len(valid) / max(len(win), 1)
    run = best = 0
    for r in win:
        if r["quality_flag"] == OK and r["value"] is not None and r["value"] <= th.recovery_temp_c:
            run += 1
            best = max(best, run)
        elif r["quality_flag"] == OK:
            run = 0
    metrics = {
        "window_index": window_index,
        "window_s": th.verify_window_s,
        "valid_samples": len(valid),
        "valid_ratio": round(ratio, 3),
        "recovery_temp_c": th.recovery_temp_c,
        "longest_below_s": best,
        "required_below_s": th.recovery_sustain_s,
        "mean_c": round(sum(r["value"] for r in valid) / len(valid), 2) if valid else None,
        "last_c": round(valid[-1]["value"], 2) if valid else None,
        "command_status": action["command_status"],
    }
    # TODO(학생) 3: 명령이 성공했고 마지막 값이 경보 온도 아래면 회복으로 본다 — 명령 성공은 회복이 아니다.
    if action["command_status"] == "SUCCEEDED" and metrics["last_c"] is not None and metrics["last_c"] < th.alarm_temp_c:
        outcome = "RECOVERED"
    elif ratio < th.verify_min_valid_ratio:
        outcome = "INSUFFICIENT_DATA"
    elif best >= th.recovery_sustain_s:
        outcome = "RECOVERED"
    else:
        outcome = "NOT_IMPROVED"
    return {"outcome": outcome, "window_start": start, "window_end": end, "metrics": metrics}
