"""교재·영상용 중간 결과물 그림 — 모두 실제 데이터와 실제 실행 결과로 그린다.

출력: lecture/materials/figures/*.png  (+ figures_data.json: 그림에 쓴 수치)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT.parent / "materials" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

from hydops.b1_data import uci  # noqa: E402
from hydops.b1_data.simulator import HydraulicSimulator  # noqa: E402
from hydops.b2_quality.checks import SensorQualityChecker  # noqa: E402
from hydops.b5_detect import evaluate  # noqa: E402
from hydops.b5_detect.detector import PhaseBaseline, ThresholdDetector, detect_cycle_phase  # noqa: E402
from hydops.config import TH  # noqa: E402

# 참조 팔레트 (dataviz reference instance, light)
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
CRIT, GOOD, WARN = "#d92d20", "#067647", "#b54708"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e7e6e2", "#fcfcfb"
FLAG_COL = {"MISSING": CRIT, "GAP": CRIT, "SPIKE": "#4a3aa7", "STUCK": WARN, "OUT_OF_RANGE": CRIT}

plt.rcParams.update({
    "font.family": "Pretendard", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "lines.linewidth": 2, "axes.titleweight": "bold", "axes.titlesize": 13,
    "axes.unicode_minus": False,
})
DATA: dict = {}


def save(fig, name, note=""):
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=160)
    plt.close(fig)
    print("saved", name, note)


def fig_uci_reduction(ds):
    raw_ps = uci.load_sensor_matrix("PS1")[100]
    raw_fs = uci.load_sensor_matrix("FS1")[100]
    red = ds.sensors
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    t = np.arange(60)
    ax = axes[0]
    ax.plot(t, red["TS1"]["mean"][100], color=S1)
    ax.set_title("TS1 온도 · 1 Hz → 그대로 사용")
    ax.set_xlabel("사이클 내 경과 초 (elapsed_s)"); ax.set_ylabel("°C")
    ax = axes[1]
    ax.plot(np.arange(6000) / 100, raw_ps, color=GRID, linewidth=0.6, label="원시 100 Hz")
    ax.fill_between(t + 0.5, red["PS1"]["min"][100], red["PS1"]["max"][100], color=S1, alpha=0.18, label="1초 최솟값~최댓값")
    ax.plot(t + 0.5, red["PS1"]["mean"][100], color=S1, label="1초 평균")
    ax.set_title("PS1 압력 · 100 Hz → 1초 평균·최솟값·최댓값"); ax.set_xlabel("경과 초"); ax.set_ylabel("bar"); ax.legend(frameon=False, fontsize=9)
    ax = axes[2]
    ax.plot(np.arange(600) / 10, raw_fs, color=GRID, linewidth=0.8, label="원시 10 Hz")
    ax.plot(t + 0.5, red["FS1"]["mean"][100], color=S1, label="1초 평균 (n=10 추적)")
    ax.set_title("FS1 유량 · 10 Hz → 1초 평균"); ax.set_xlabel("경과 초"); ax.set_ylabel("L/min"); ax.legend(frameon=False, fontsize=9)
    fig.suptitle("B1 · UCI 사이클 #100 을 공통 관측 형식(1초)으로 축약", fontweight="bold", x=0.01, ha="left")
    save(fig, "F01_uci_1s_reduction")


def fig_cooler_states(ds):
    temps, prof = ds.sensors["TS1"]["mean"], ds.profile
    fig, ax = plt.subplots(figsize=(10, 4.4))
    stats = {}
    for c, col, lab in ((100, S1, "냉각기 100% (정상)"), (20, S2, "냉각기 20% (저하)"), (3, S3, "냉각기 3% (고장 직전)")):
        ids = prof.index[(prof.cooler_pct == c) & (prof.stable_flag == 0)].to_numpy()
        m, lo, hi = temps[ids].mean(0), np.percentile(temps[ids], 5, 0), np.percentile(temps[ids], 95, 0)
        ax.fill_between(range(60), lo, hi, color=col, alpha=0.15, linewidth=0)
        ax.plot(range(60), m, color=col, label=f"{lab} · {len(ids)}사이클")
        stats[c] = {"cycles": int(len(ids)), "mean_c": round(float(m.mean()), 2)}
    ax.set_title("UCI 온도(TS1)는 냉각기 상태에 따라 뚜렷이 달라진다 — 안정 상태 사이클, 5~95% 구간")
    ax.set_xlabel("사이클 내 경과 초"); ax.set_ylabel("°C"); ax.legend(frameon=False, loc="center right")
    ax.text(0, 30.5, "profile 의 냉각기 상태는 정답 평가에만 쓰고 탐지 입력에서는 뺀다", color=INK2, fontsize=10)
    ax.set_ylim(29, 62)
    DATA["cooler_states"] = stats
    save(fig, "F02_uci_cooler_states")


def fig_quality(ds):
    rows = uci.inject_sensor_errors(uci.cycle_observations(ds, 1500, "HYD-01", datetime(2026, 11, 7, tzinfo=timezone.utc)))
    checked = [r for r in SensorQualityChecker().check_many(rows) if r["sensor_id"] == "TS1"]
    t = np.array([r["elapsed_s"] for r in checked])
    raw = np.array([np.nan if r["raw_value"] is None else r["raw_value"] for r in checked])
    clean = np.array([np.nan if r["value"] is None else r["value"] for r in checked])
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax = axes[0]
    ax.plot(t, raw, color=GRID, linewidth=3, label="원시 값 raw_value (보존)")
    ax.plot(t, clean, color=S1, label="정제 값 value (OK 일 때만)")
    counts = {}
    for r in checked:
        f = r["quality_flag"]
        counts[f] = counts.get(f, 0) + 1
        if f != "OK":
            y = r["raw_value"] if r["raw_value"] is not None else np.nanmin(raw) - 0.6
            ax.scatter([r["elapsed_s"]], [y], s=46, color=FLAG_COL[f], zorder=5, edgecolor=SURF, linewidth=1.5)
    for f, lab in (("SPIKE", "급등"), ("GAP", "긴 결측 → 판정 보류"), ("STUCK", "고착")):
        xs = [r["elapsed_s"] for r in checked if r["quality_flag"] == f]
        if xs:
            yy = next((r["raw_value"] for r in checked if r["quality_flag"] == f and r["raw_value"] is not None), np.nanmin(raw) - 0.6)
            ax.annotate(f"{lab} ({f})", (xs[0], yy), xytext=(10, 4), textcoords="offset points", fontsize=10, color=INK)
    ax.set_title("B2 · 오류 주입본(사이클 #1500): 원시 값은 남기고, 품질이 나쁜 관측은 정제 값에서 비운다", pad=14)
    ax.set_ylim(np.nanmin(raw) - 2, np.nanmax(raw) + 6)
    ax.set_ylabel("°C"); ax.legend(frameon=False, loc="upper right", fontsize=9.5)
    ax = axes[1]
    order = ["OK", "MISSING", "GAP", "SPIKE", "STUCK"]
    ypos = {f: i for i, f in enumerate(order)}
    for r in checked:
        ax.scatter(r["elapsed_s"], ypos[r["quality_flag"]], s=18, color=S1 if r["quality_flag"] == "OK" else FLAG_COL[r["quality_flag"]], marker="s")
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=9); ax.set_xlabel("사이클 내 경과 초"); ax.grid(False)
    DATA["quality_flags"] = counts
    save(fig, "F03_quality_flags", counts)


def fig_phase_baseline(ds):
    _, baseline_ids, test_ids = evaluate.fixed_split()
    temps = ds.sensors["TS1"]["mean"]
    bl = PhaseBaseline.fit(temps, baseline_ids)
    cid = next(c for c in test_ids if int(ds.profile.loc[c, "cooler_pct"]) == 20)
    ncid = next(c for c in test_ids if int(ds.profile.loc[c, "cooler_pct"]) == 100)
    r = detect_cycle_phase(temps[cid], bl)
    rn = detect_cycle_phase(temps[ncid], bl)
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.4))
    ax = axes[0]
    m, s = np.array(bl.mean), np.array(bl.std)
    ax.fill_between(range(60), m - 4 * s, m + np.maximum(4 * s, 3), color=S1, alpha=0.14, label="정상 위상 기준 ± 허용폭")
    ax.plot(range(60), m, color=S1, label=f"정상 기준 평균 ({len(baseline_ids)}사이클)")
    ax.plot(range(60), temps[ncid], color=S3, label=f"시험 #{ncid} 냉각기 100%")
    ax.plot(range(60), temps[cid], color=S2, label=f"시험 #{cid} 냉각기 20%")
    ax.set_title("같은 위상끼리 비교한다"); ax.set_xlabel("사이클 내 경과 초"); ax.set_ylabel("°C"); ax.legend(frameon=False, fontsize=9)
    ax = axes[1]
    ax.plot(range(60), r["residual"], color=S2, label=f"#{cid} 잔차")
    ax.plot(range(60), rn["residual"], color=S3, label=f"#{ncid} 잔차")
    ax.plot(range(60), r["limit"], color=CRIT, linestyle="--", linewidth=1.5, label="허용 한계 max(4σ, 3°C)")
    if r["first_alarm_s"] is not None:
        ax.axvspan(r["first_alarm_s"] - 9, r["first_alarm_s"], color=CRIT, alpha=0.08)
        ax.annotate(f"10초 연속 초과 → 감지 (지연 {r['first_alarm_s']}초)", (r["first_alarm_s"], r["residual"][r["first_alarm_s"]]), xytext=(10, -30), textcoords="offset points", arrowprops={"arrowstyle": "->", "color": INK2}, fontsize=10)
    ax.set_title("이동평균 잔차가 지속될 때만 이상"); ax.set_xlabel("사이클 내 경과 초"); ax.set_ylabel("°C 차이"); ax.legend(frameon=False, fontsize=9, loc="center right")
    fig.suptitle("B5 · 정상 위상 기준과 이동 통계 (UCI TS1)", fontweight="bold", x=0.01, ha="left")
    save(fig, "F04_phase_baseline_residual")


def fig_eval_compare():
    from hydops.config import Thresholds

    grid = []
    for k, dl in ((2.0, 1.0), (4.0, 3.0)):
        for su in (1, 10):
            r = evaluate.evaluate(k_sigma=k, min_delta_c=dl, sustain_s=su, smooth_s=5)
            r.pop("rows")
            grid.append({"k_sigma": k, "min_delta_c": dl, "sustain_s": su, "tp": r["tp"], "fp": r["fp"], "fn": r["fn"], "delay_s": r["mean_delay_s"], "baseline": r["baseline_cycles"], "test": r["test_cycles"]})
    near = []
    for T in (59.8, 60.2):
        for su in (1, 3, 5, 10):
            sim = HydraulicSimulator(seed=11, temp_c=T)
            sim.inject_cooling_degradation(15 / (T - 30))
            chk, det = SensorQualityChecker(), ThresholdDetector(Thresholds(alarm_sustain_s=su))
            n = 0
            for _ in range(600):
                for r in chk.check_many(sim.step()):
                    n += sum(1 for x in det.feed(r) if x.event_type == "COOLING_ANOMALY")
            near.append({"steady_c": T, "sustain_s": su, "alarm_signals_600s": n})
    DATA["eval"] = {"uci_grid": grid, "simulator_near_threshold": near}

    fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    labels = ["2σ · 최소 1°C", "4σ · 최소 3°C"]
    xs = np.arange(2)
    for i, (su, col) in enumerate(((1, S2), (10, S1))):
        vals = [g["fp"] for g in grid if g["sustain_s"] == su]
        dls = [g["delay_s"] for g in grid if g["sustain_s"] == su]
        bars = ax.bar(xs + (i - 0.5) * 0.36, vals, width=0.34, color=col, label=f"지속 {su}초")
        for b, v, d in zip(bars, vals, dls):
            ax.text(b.get_x() + b.get_width() / 2, v, f"오탐 {v}\n지연 {d:.0f}초", ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(xs); ax.set_xticklabels(labels); ax.set_ylim(0, 6.5); ax.set_ylabel("오탐 (정상 60사이클 중)")
    ax.grid(axis="x", visible=False); ax.legend(frameon=False, loc="upper right")
    ax.set_title("UCI 고정 시험 구간 — 오탐을 줄인 것은 임계값, 지속은 지연만 늘렸다", fontsize=12)
    ax.text(0, 6.0, "누락은 모든 조합에서 0/120", fontsize=10, color=INK2)
    ax = axes[1]
    sus = [1, 3, 5, 10]
    for T, col, lab in ((59.8, S2, "정상 상한 근처 59.8°C 에서 떨림"), (60.2, CRIT, "실제로 60.2°C 를 넘은 상태")):
        ys = [n["alarm_signals_600s"] for n in near if n["steady_c"] == T]
        ax.plot(sus, ys, marker="o", markersize=8, color=col, label=lab)
        for x, y in zip(sus, ys):
            ax.annotate(str(y), (x, y), xytext=(12, 8) if T > 60 else (-12, -16), textcoords="offset points", ha="center", fontsize=10)
    ax.set_xticks(sus); ax.set_xlabel("지속 조건 (초)"); ax.set_ylabel("경보 신호 수 (10분)"); ax.set_ylim(-5, 120)
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("시뮬레이터 — 지속 조건은 임계값 근처의 떨림을 걸러낸다", fontsize=12)
    fig.suptitle("B5 · 무엇이 오탐을 줄이나: 임계값과 지속 조건은 하는 일이 다르다", fontweight="bold", x=0.01, ha="left")
    save(fig, "F05_detection_eval_compare", {"grid": [(g["k_sigma"], g["sustain_s"], g["fp"], g["delay_s"]) for g in grid], "near": [(n["steady_c"], n["sustain_s"], n["alarm_signals_600s"]) for n in near]})


def sim_run(cooling, act_at=None, load=0.8, seconds=200, seed=7, dropout=None):
    sim = HydraulicSimulator(seed=seed)
    chk, det = SensorQualityChecker(), ThresholdDetector()
    temps, flags, alarm_t = [], [], None
    for s in range(seconds):
        if s == 20:
            sim.inject_cooling_degradation(cooling)
        if dropout and s == dropout[0]:
            sim.inject_sensor_fault("dropout", dropout[1])
        if act_at is not None and s == act_at:
            sim.apply_load(load)
        rows = chk.check_many(sim.step())
        ts = next(r for r in rows if r["sensor_id"] == "TS1")
        temps.append(ts["raw_value"])
        flags.append(ts["quality_flag"])
        for sig in [x for r in rows for x in det.feed(r)]:
            if sig.event_type == "COOLING_ANOMALY" and alarm_t is None:
                alarm_t = s
    return np.array([np.nan if v is None else v for v in temps]), flags, alarm_t


def fig_closed_loop():
    base, _, alarm = sim_run(0.4)
    act_at = alarm + 15  # 근거 확인·승인에 걸린 시간 가정
    acted, _, _ = sim_run(0.4, act_at=act_at)
    t = np.arange(len(base))
    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.plot(t, base, color=S2, label="조치 없음 (같은 초기 상태·시드 7)")
    ax.plot(t, acted, color=S1, label="승인 후 부하 1.0 → 0.8")
    ax.axhline(TH.alarm_temp_c, color=CRIT, linestyle="--", linewidth=1.3); ax.text(2, TH.alarm_temp_c + 0.6, "경보 60°C · 10초 지속", color=CRIT, fontsize=10)
    ax.axhline(TH.recovery_temp_c, color=GOOD, linestyle="--", linewidth=1.3); ax.text(2, TH.recovery_temp_c - 1.8, "회복 55°C 이하 · 10초 유지", color=GOOD, fontsize=10)
    ax.axvline(20, color=INK2, linewidth=1); ax.text(21, 44.2, "냉각 성능 0.4 주입", fontsize=10, color=INK2)
    ax.axvline(alarm, color=CRIT, linewidth=1); ax.text(alarm + 1, 69, f"감지 t={alarm}s", fontsize=10, color=CRIT)
    ax.axvline(act_at, color=S1, linewidth=1.5); ax.text(act_at + 1, 70.5, "승인 조치 실행", fontsize=10, color=S1)
    ax.axvspan(act_at + TH.verify_wait_s, act_at + TH.verify_wait_s + TH.verify_window_s, color=S3, alpha=0.12)
    ax.text(act_at + TH.verify_wait_s + 2, 47, "재측정 창 (조치 30초 후 60초)\n조치 이후 관측만 본다", fontsize=10, color=INK)
    ax.set_title("B8→B1→B2→B3→B5 · 폐루프: 명령 성공이 아니라 새 관측의 회복으로 종결한다 (합성 시뮬레이터)")
    ax.set_xlabel("시뮬레이터 경과 초"); ax.set_ylabel("탱크 온도 °C"); ax.legend(frameon=False, loc="lower right"); ax.set_ylim(42, 73)
    DATA["closed_loop"] = {"alarm_s": int(alarm), "act_s": int(act_at), "no_action_last20_min": round(float(np.nanmin(base[-20:])), 2), "acted_last20_max": round(float(np.nanmax(acted[-20:])), 2)}
    save(fig, "F06_closed_loop_same_seed", DATA["closed_loop"])


def fig_outcomes():
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharey=True)
    cases = [("회복 → 종결", 0.4, None, GOOD), ("미개선 → 담당자 이관", 0.25, None, CRIT), ("데이터 부족 → 재측정 보류", 0.4, (95, 45), WARN)]
    out = {}
    for ax, (title, cool, drop, col) in zip(axes, cases):
        temps, flags, alarm = sim_run(cool, act_at=None, seconds=1)
        temps, flags, alarm = sim_run(cool, seconds=10)  # placeholder to get alarm
        _, _, alarm = sim_run(cool, seconds=120)
        act = alarm + 15
        temps, flags, _ = sim_run(cool, act_at=act, seconds=act + 30 + 60 + 10, dropout=drop)
        t = np.arange(len(temps))
        ax.plot(t, temps, color=S1)
        bad = [i for i, f in enumerate(flags) if f != "OK"]
        if bad:
            ax.scatter(bad, [42] * len(bad), s=10, color=CRIT, marker="|", label="결측(GAP/MISSING)")
            ax.legend(frameon=False, loc="upper right", fontsize=9)
        w0, w1 = act + 30, act + 90
        ax.axvspan(w0, w1, color=S3, alpha=0.12)
        ax.axhline(TH.alarm_temp_c, color=CRIT, linestyle="--", linewidth=1.1)
        ax.axhline(TH.recovery_temp_c, color=GOOD, linestyle="--", linewidth=1.1)
        ax.axvline(act, color=S1, linewidth=1.3)
        win = [(v, f) for v, f in zip(temps[w0:w1], flags[w0:w1])]
        valid = [v for v, f in win if f == "OK"]
        run = best = 0
        for v, f in win:
            if f == "OK" and v <= TH.recovery_temp_c:
                run += 1; best = max(best, run)
            elif f == "OK":
                run = 0
        ratio = len(valid) / 60
        verdict = "INSUFFICIENT_DATA" if ratio < 0.7 else "RECOVERED" if best >= 10 else "NOT_IMPROVED"
        out[title] = {"valid_ratio": round(ratio, 2), "longest_below_s": best, "verdict": verdict}
        ax.set_title(title, color=INK)
        ax.text(w0 + 1, 74, f"유효 {ratio:.0%} · 55°C 이하 연속 {best}초\n판정 {verdict}", fontsize=10, color=INK)
        ax.set_xlabel("경과 초")
    axes[0].set_ylabel("°C"); axes[0].set_ylim(41, 82)
    fig.suptitle("B8 · 재측정 판정의 세 갈래 — 같은 조치(부하 0.8), 다른 결과", fontweight="bold", x=0.01, ha="left")
    DATA["outcomes"] = out
    save(fig, "F07_verification_outcomes", out)


def fig_graph():
    from hydops.b4_ontology import graph

    assets = ["HYD-01", "HYD-02", "HYD-03"]
    sensors = graph.run("MATCH (a:Asset)-[:HAS_SENSOR]->(s:Sensor) RETURN a.asset_id AS a, s.sensor_id AS s ORDER BY s")
    applies = graph.run("MATCH (s:SOP)-[:APPLIES_TO]->(a:Asset) RETURN s.sop_key AS s, a.asset_id AS a, s.status AS st")
    allows = graph.run("MATCH (s:SOP)-[:ALLOWS]->(x:Action) RETURN s.sop_key AS s, x.action_id AS x")
    sops = sorted({r["s"] for r in applies}, key=lambda k: (k.split("@")[0], k))
    status = {r["s"]: r["st"] for r in applies}
    actions = ["REDUCE_LOAD", "FAN_BOOST", "SENSOR_CHECK", "ESCALATE"]
    pos = {}
    ay = {"HYD-01": 7.2, "HYD-02": 3.4, "HYD-03": 0.6}
    for a in assets:
        pos[a] = (3.2, ay[a])
    for a in assets:
        ss = [r["s"] for r in sensors if r["a"] == a]
        for i, sid in enumerate(ss):
            pos[sid] = (0.6, ay[a] + (1 - i) * 0.75)
    for i, k in enumerate(sops):
        pos[k] = (6.6, 8.2 - i * 1.15)
    for i, x in enumerate(actions):
        pos[x] = (10.0, 7.4 - i * 1.9)
    fig, ax = plt.subplots(figsize=(14, 8.4))
    ax.axis("off"); ax.set_xlim(-0.6, 11.4); ax.set_ylim(-0.4, 9.2)

    def edge(u, v, col="#b9b8b3", lw=1.3, ls="-"):
        ax.annotate("", xy=pos[v], xytext=pos[u], arrowprops={"arrowstyle": "-|>", "color": col, "lw": lw, "linestyle": ls, "shrinkA": 22, "shrinkB": 22})

    for r in sensors:
        edge(r["a"], r["s"])
    for r in applies:
        edge(r["s"], r["a"], col=S2 if r["st"] == "active" else "#d6d5d0", ls="-" if r["st"] == "active" else "--")
    for r in allows:
        edge(r["s"], r["x"], col="#8f86d9")
    for n, (x, y) in pos.items():
        if n in assets:
            col, size, lab = S1, 2600, n
        elif n in actions:
            col, size, lab = "#4a3aa7", 1500, n
        elif "@" in n:
            col, size, lab = (S2 if status.get(n) == "active" else "#d6d5d0"), 1500, n.replace("@v", " v")
        else:
            col, size, lab = S3, 700, n.split(".")[1]
        ax.scatter([x], [y], s=size, color=col, edgecolor=SURF, linewidth=2, zorder=3)
        dx = {S3: -0.35}.get(col, 0)
        ax.text(x + (dx if col == S3 else 0), y - (0 if col == S3 else 0.42), lab, ha="right" if col == S3 else "center", va="center" if col == S3 else "top", fontsize=9.5, color=INK, zorder=4)
    for x, t in ((0.6, "Sensor (Measure)"), (3.2, "Asset (Resource)"), (6.6, "SOP · 문서 ID@버전"), (10.0, "Action · 허용 조치")):
        ax.text(x, 9.0, t, ha="center", fontsize=11, fontweight="bold", color=INK2)
    ax.text(3.2, 1.35, "HYD-03 (신규): 적용 SOP 없음 → 근거 없음 보류", ha="center", fontsize=9.5, color=CRIT)
    ax.text(6.6, -0.25, "회색 점선 = 폐기(superseded) 판 — 검색·질의에서 제외", ha="center", fontsize=9.5, color=INK2)
    ax.set_title("B4 · Neo4j 설비 관계: HAS_SENSOR · APPLIES_TO · ALLOWS — 설비마다 다른 SOP·허용 조치 (시계열은 그래프에 넣지 않는다)", loc="left")
    save(fig, "F08_neo4j_asset_graph")


def fig_sop_filter():
    from hydops.b6_sop.search import search_sop

    res = {a: search_sop(a, "COOLING_ANOMALY", k=5)["hits"] for a in ("HYD-01", "HYD-02")}
    sup = search_sop("HYD-01", "COOLING_ANOMALY", "부하를 얼마로 낮추나 허용 조치", k=5, include_superseded=True)["hits"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.9))
    for ax, (title, hits) in zip(axes, [("HYD-01 · 냉각 이상 (active)", res["HYD-01"]), ("HYD-02 · 냉각 이상 (active)", res["HYD-02"]), ("HYD-01 · 폐기본 포함 (필터 해제)", sup)]):
        labels = [f"{h['doc_id']} v{h['version']} §{h['section']} {h['heading']}" for h in hits][::-1]
        scores = [h["score"] for h in hits][::-1]
        cols = [CRIT if (h["doc_id"] == "SOP-COOL-001" and h["version"] == 1) else S1 for h in hits][::-1]
        ax.barh(labels, scores, color=cols, height=0.6)
        for i, s in enumerate(scores):
            ax.text(s, i, f" {s:.3f}", va="center", fontsize=9, color=INK)
        ax.set_xlim(min(scores) - 0.05, max(scores) + 0.03)
        ax.set_title(title); ax.tick_params(axis="y", labelsize=9); ax.grid(axis="y", visible=False)
    fig.suptitle("B6 · Neo4jVector SOP 검색 — 설비·버전 필터가 근거의 범위를 정한다 (빨강 = 폐기된 1판)", fontweight="bold", x=0.01, ha="left")
    DATA["sop_filter"] = {k: [f"{h['doc_id']}@v{h['version']}#{h['section']}" for h in v] for k, v in {**res, "HYD-01+superseded": sup}.items()}
    save(fig, "F09_sop_search_filter")


def fig_zeroshot():
    from hydops.b5_detect import zeroshot

    pipe = zeroshot.load_pipeline()
    sim = zeroshot.simulator_case(pipe)
    uci_res = zeroshot.uci_compare(pipe)
    x, band = sim["series"], sim["band"]
    t = np.arange(len(x))
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.4), gridspec_kw={"width_ratios": [1.7, 1]})
    ax = axes[0]
    ax.fill_between(t, band["q10"], band["q90"], color=S2, alpha=0.18, linewidth=0, label="Chronos-Bolt 예측 10~90% 구간")
    ax.plot(t, band["q50"], color=S2, linewidth=1.3, linestyle="--", label="예측 중앙값")
    ax.plot(t, x, color=S1, label="관측 온도")
    ax.axvline(sim["inject_s"], color=INK2, linewidth=1); ax.text(sim["inject_s"] + 1, 46.5, "냉각 0.4 주입", fontsize=10, color=INK2)
    ax.axvline(sim["zeroshot_alarm_s"], color=S2, linewidth=1.6); ax.text(sim["zeroshot_alarm_s"] - 1, 57, f"예측 이탈 5초\n→ t={sim['zeroshot_alarm_s']}", fontsize=10, color=INK, ha="right")
    ax.axvline(sim["rule_alarm_s"], color=CRIT, linewidth=1.6); ax.text(sim["rule_alarm_s"] + 2, 56, f"규칙 60°C·10초\n→ t={sim['rule_alarm_s']}", fontsize=10, color=CRIT)
    ax.axhline(60, color=CRIT, linestyle=":", linewidth=1)
    ax.set_title("시뮬레이터: 갑작스러운 변화는 예측 이탈이 먼저 알린다"); ax.set_xlabel("경과 초"); ax.set_ylabel("°C"); ax.legend(frameon=False, fontsize=9, loc="lower right"); ax.set_ylim(43, 72)
    ax = axes[1]
    labels = ["냉각기 100%\n(정상)", "냉각기 20%", "냉각기 3%"]
    zs = [uci_res[k]["alarms"] for k in ("100", "20", "3")]
    ev = evaluate.evaluate()
    rows = ev["rows"]
    ph = [sum(1 for r in rows if r["cooler_pct"] == c and r["pred"] and r["cycle"] in {x["cycle"] for x in rows if x["cooler_pct"] == c}) for c in (100, 20, 3)]
    n = [uci_res[k]["cycles"] for k in ("100", "20", "3")]
    ph_rate = [sum(1 for r in rows if r["cooler_pct"] == c and r["pred"]) / sum(1 for r in rows if r["cooler_pct"] == c) for c in (100, 20, 3)]
    xs = np.arange(3)
    ax.bar(xs - 0.18, ph_rate, width=0.34, color=S1, label="위상 기준 (정상 사이클과 비교)")
    ax.bar(xs + 0.18, [z / m for z, m in zip(zs, n)], width=0.34, color=S2, label="zero-shot (그 사이클의 과거로 예측)")
    for i, v in enumerate(ph_rate):
        ax.text(i - 0.18, v, f"{v:.0%}", ha="center", va="bottom", fontsize=10)
    for i, (z, m) in enumerate(zip(zs, n)):
        ax.text(i + 0.18, z / m, f"{z}/{m}", ha="center", va="bottom", fontsize=10)
    ax.set_xticks(xs); ax.set_xticklabels(labels); ax.set_ylim(0, 1.55); ax.set_ylabel("경보 비율"); ax.grid(axis="x", visible=False)
    ax.set_title("UCI: 처음부터 저하된 사이클은 예측이 그대로 따라간다"); ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle("B5 선택 실습 · 사전학습 시계열 모델 zero-shot 예측과 규칙·위상 기준 비교 — 역할이 다르다", fontweight="bold", x=0.01, ha="left")
    DATA["zeroshot"] = {"simulator": {k: sim[k] for k in ("inject_s", "rule_alarm_s", "zeroshot_alarm_s")}, "uci": uci_res, "phase_rate": ph_rate}
    save(fig, "F10_zeroshot_vs_rules", DATA["zeroshot"])


if __name__ == "__main__":
    ds = uci.load_reduced()
    fig_uci_reduction(ds)
    fig_cooler_states(ds)
    fig_quality(ds)
    fig_phase_baseline(ds)
    fig_eval_compare()
    fig_closed_loop()
    fig_outcomes()
    fig_graph()
    fig_sop_filter()
    fig_zeroshot()
    (OUT / "figures_data.json").write_text(json.dumps(DATA, ensure_ascii=False, indent=2, default=str))
