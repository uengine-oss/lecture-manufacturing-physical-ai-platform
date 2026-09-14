"""B5 선택 실습 · 사전학습 시계열 모델(Chronos-Bolt)의 zero-shot 예측 비교.

- 추가 학습 없이 기존 체크포인트로 다음 구간을 예측한다 (설치·추론은 강사가 미리 준비).
- 입력은 미래를 포함하지 않는다: t 시점까지의 관측만 넣고 t+1..t+H 를 예측한다.
- 예측 오차·구간 이탈을 이상 점수로 바꾸는 기준과 지속 조건은 별도로 설계해야 한다 — 여기서는
  '관측이 예측 90% 상한을 넘은 상태가 sustain_s 연속'을 이상으로 둔다.
- 규칙 기반 감지는 zero-shot 모델이라고 부르지 않는다. 필수 경로는 여전히 규칙과 이동 통계다.

사용: PYTHONPATH=. .venv/bin/python -m hydops.b5_detect.zeroshot
"""
from __future__ import annotations

import json

import numpy as np

MODEL_ID = "amazon/chronos-bolt-tiny"


def load_pipeline():
    import torch
    from chronos import BaseChronosPipeline

    return BaseChronosPipeline.from_pretrained(MODEL_ID, device_map="cpu", torch_dtype=torch.float32)


def rolling_forecast_band(pipe, series: np.ndarray, context_s: int = 30, horizon: int = 5) -> dict:
    """series 를 horizon 간격으로 굴리며 예측한다. 각 시점 예측에는 그 시점 이전 값만 쓴다."""
    import torch

    n = len(series)
    q10, q50, q90 = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    starts = list(range(context_s, n, horizon))
    ctx = [torch.tensor(series[max(0, s - context_s) : s], dtype=torch.float32) for s in starts]
    quant, _ = pipe.predict_quantiles(ctx, prediction_length=horizon, quantile_levels=[0.1, 0.5, 0.9])
    for i, s in enumerate(starts):
        e = min(s + horizon, n)
        q10[s:e], q50[s:e], q90[s:e] = (quant[i, : e - s, k].numpy() for k in range(3))
    return {"q10": q10, "q50": q50, "q90": q90}


def band_alarm(series, band, sustain_s: int = 5, margin: float = 0.5):
    above = series > band["q90"] + margin
    run, first = 0, None
    for i, a in enumerate(above):
        run = run + 1 if a else 0
        if run >= sustain_s and first is None:
            first = i
    return first


def simulator_case(pipe, seed=7):
    from hydops.b1_data.simulator import HydraulicSimulator

    sim = HydraulicSimulator(seed=seed)
    temps = []
    for s in range(150):
        if s == 60:
            sim.inject_cooling_degradation(0.4)
        temps.append(next(r["raw_value"] for r in sim.step() if r["sensor_id"] == "TS1"))
    x = np.array(temps)
    band = rolling_forecast_band(pipe, x, context_s=30, horizon=5)
    first = band_alarm(x, band)
    rule = next((i for i in range(10, len(x)) if all(v > 60 for v in x[i - 9 : i + 1])), None)
    return {"series": x, "band": band, "zeroshot_alarm_s": first, "rule_alarm_s": rule, "inject_s": 60}


def uci_compare(pipe, per_class: int = 20):
    """UCI 고정 시험 구간 일부에서: 사이클 앞 30초로 뒤 30초를 예측해 이탈 여부를 본다.

    한 사이클 안에서 냉각기 상태는 변하지 않으므로 zero-shot 예측은 '그 사이클의 과거'를 따라가 버린다.
    → 위상 기준(정상 사이클과 비교)은 잡는 이상을 zero-shot 예측은 거의 못 잡는다. 이것이 비교 실습의 요점이다.
    """
    from hydops.b5_detect import evaluate

    ds, _, test_ids = evaluate.fixed_split()
    temps = ds.sensors["TS1"]["mean"]
    rows = []
    for c in (100, 20, 3):
        ids = [i for i in test_ids if int(ds.profile.loc[i, "cooler_pct"]) == c][:per_class]
        for cid in ids:
            band = rolling_forecast_band(pipe, temps[cid], context_s=30, horizon=5)
            rows.append({"cycle": int(cid), "cooler_pct": c, "alarm": band_alarm(temps[cid], band) is not None})
    out = {}
    for c in (100, 20, 3):
        rs = [r for r in rows if r["cooler_pct"] == c]
        out[str(c)] = {"cycles": len(rs), "alarms": sum(r["alarm"] for r in rs)}
    return out


if __name__ == "__main__":
    pipe = load_pipeline()
    sim = simulator_case(pipe)
    print("simulator", {k: sim[k] for k in ("inject_s", "rule_alarm_s", "zeroshot_alarm_s")})
    print("uci", json.dumps(uci_compare(pipe), ensure_ascii=False))
