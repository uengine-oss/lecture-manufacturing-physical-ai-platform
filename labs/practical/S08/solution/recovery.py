"""S08 · 조치 후 재측정 판정 (정답본).

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
    # 창 안(start < ts <= end)의 관측만 쓴다. 조치 전 관측은 회복 근거가 아니다.
    win = sorted((r for r in rows if r["sensor_id"] == sensor_id and start < r["ts"] <= end), key=lambda r: r["ts"])
    valid = [r for r in win if r["quality_flag"] == OK and r["value"] is not None]
    # 유효 비율의 분모는 창 길이(초)다. 결측 행을 먼저 지우면 비율이 항상 100% 가 된다.
    ratio = len(valid) / th.verify_window_s
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
        "command_status": action["command_status"],  # 기록만 한다. 판정에 쓰지 않는다.
    }
    if ratio < th.verify_min_valid_ratio:
        outcome = "INSUFFICIENT_DATA"
    elif best >= th.recovery_sustain_s:
        outcome = "RECOVERED"
    else:
        outcome = "NOT_IMPROVED"
    return {"outcome": outcome, "window_start": start, "window_end": end, "metrics": metrics}
