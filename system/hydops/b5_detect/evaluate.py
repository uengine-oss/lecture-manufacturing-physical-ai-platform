"""B5 · UCI 사건 단위 평가. 임계값을 정하는 기준 구간과 최종 평가 사이클을 분리하고 시험 구간을 고정한다.

정답(profile.cooler_pct)은 평가에만 쓰고 탐지 입력에서 제외한다.
정답 정의: cooler_pct < 100 (냉각 성능 저하 20% 또는 고장 직전 3%) → 이상 사이클.
"""
from __future__ import annotations

import numpy as np

from hydops.b1_data.uci import load_reduced
from hydops.b5_detect.detector import PhaseBaseline, detect_cycle_phase

SPLIT_SEED = 2026


def fixed_split():
    ds = load_reduced()
    prof = ds.profile
    normal_stable = prof.index[(prof.cooler_pct == 100) & (prof.stable_flag == 0)].to_numpy()
    rng = np.random.default_rng(SPLIT_SEED)
    baseline = np.sort(rng.choice(normal_stable, size=len(normal_stable) // 2, replace=False))
    rest = np.setdiff1d(prof.index.to_numpy(), baseline)
    # 시험 구간: 기준에 쓰지 않은 사이클에서 상태별 60개씩 고정 추출
    test = []
    for c in (100, 20, 3):
        pool = np.intersect1d(rest, prof.index[prof.cooler_pct == c].to_numpy())
        test.extend(np.sort(rng.choice(pool, size=60, replace=False)).tolist())
    return ds, baseline, sorted(test)


def evaluate(k_sigma=4.0, min_delta_c=3.0, sustain_s=10, smooth_s=5):
    ds, baseline_ids, test_ids = fixed_split()
    temps = ds.sensors["TS1"]["mean"]
    bl = PhaseBaseline.fit(temps, baseline_ids)
    tp = fp = fn = tn = 0
    delays = []
    rows = []
    for cid in test_ids:
        r = detect_cycle_phase(temps[cid], bl, k_sigma, min_delta_c, sustain_s, smooth_s)
        truth = int(ds.profile.loc[cid, "cooler_pct"]) < 100
        if r["is_anomaly"] and truth:
            tp += 1
            delays.append(r["first_alarm_s"])
        elif r["is_anomaly"] and not truth:
            fp += 1
        elif truth:
            fn += 1
        else:
            tn += 1
        rows.append({"cycle": cid, "cooler_pct": int(ds.profile.loc[cid, "cooler_pct"]), "stable": int(ds.profile.loc[cid, "stable_flag"]) == 0, "pred": r["is_anomaly"], "delay_s": r["first_alarm_s"], "max_residual": round(r["max_residual"], 2)})
    return {
        "params": {"k_sigma": k_sigma, "min_delta_c": min_delta_c, "sustain_s": sustain_s, "smooth_s": smooth_s},
        "baseline_cycles": len(baseline_ids),
        "test_cycles": len(test_ids),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "miss_rate": round(fn / max(tp + fn, 1), 3),
        "false_alarm_rate": round(fp / max(fp + tn, 1), 3),
        "mean_delay_s": round(float(np.mean(delays)), 1) if delays else None,
        "rows": rows,
    }


if __name__ == "__main__":
    import json

    for params in ({}, {"sustain_s": 1, "smooth_s": 1, "min_delta_c": 1.0, "k_sigma": 2.0}):
        res = evaluate(**params)
        res.pop("rows")
        print(json.dumps(res, ensure_ascii=False))
