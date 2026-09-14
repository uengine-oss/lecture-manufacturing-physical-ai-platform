"""블록 단위 확인: 데이터 매핑, 품질 검사, 탐지 평가, 그래프 질의, SOP 검색, Golden Question."""
from datetime import datetime, timezone

from hydops.b1_data import uci
from hydops.b2_quality.checks import GAP, SensorQualityChecker, window_quality
from hydops.b4_ontology import graph
from hydops.b5_detect import evaluate
from hydops.b6_sop.search import search_sop
from hydops.golden import golden_questions


def test_uci_mapping_keeps_unit_source_and_cycle():
    ds = uci.load_reduced()
    rows = uci.cycle_observations(ds, 10, "HYD-01", datetime(2026, 10, 31, 14, tzinfo=timezone.utc))
    assert len(rows) == 180
    ps = [r for r in rows if r["sensor_id"] == "PS1"][0]
    assert ps["unit"] == "bar" and ps["agg"]["n"] == 100 and ps["origin_cycle_id"] == 10 and ps["is_synthetic"] is False
    assert "cooler_pct" not in rows[0]  # 정답 라벨은 탐지 입력에서 제외


def test_long_gap_is_not_hidden():
    ds = uci.load_reduced()
    rows = uci.inject_sensor_errors(uci.cycle_observations(ds, 1500, "HYD-01", datetime(2026, 11, 7, tzinfo=timezone.utc)))
    checked = [r for r in SensorQualityChecker().check_many(rows) if r["sensor_id"] == "TS1"]
    q = window_quality(checked)
    assert q["longest_gap_s"] == 7 and q["flags"][GAP] >= 3
    assert all(r["value"] is None for r in checked if r["quality_flag"] != "OK")
    assert q["flags"].get("SPIKE", 0) >= 1 and q["flags"].get("STUCK", 0) >= 1


def test_uci_eval_sustain_reduces_false_alarms():
    strict = evaluate.evaluate()
    loose = evaluate.evaluate(k_sigma=2.0, min_delta_c=1.0, sustain_s=1, smooth_s=1)
    assert strict["fp"] < loose["fp"]
    assert strict["miss_rate"] <= 0.05


def test_graph_sop_not_mixed_between_assets():
    h1 = {s["doc_id"] for s in graph.applicable_sops("HYD-01")}
    h2 = {s["doc_id"] for s in graph.applicable_sops("HYD-02")}
    assert "SOP-COOL-001" in h1 and "SOP-COOL-002" not in h1
    assert "SOP-COOL-002" in h2 and "SOP-COOL-001" not in h2


def test_sop_search_filters_asset_and_version():
    hits = search_sop("HYD-02", "COOLING_ANOMALY")["hits"]
    assert hits and all(h["doc_id"] != "SOP-COOL-001" for h in hits)
    hits1 = search_sop("HYD-01", "COOLING_ANOMALY")["hits"]
    assert all(not (h["doc_id"] == "SOP-COOL-001" and h["version"] == 1) for h in hits1)


def test_golden_questions_answerable(plant):
    from tests.helpers import run_until_settled, tick_until_event
    from hydops.b3_tsdb import store

    rt, orc = plant
    rt.tick(20)
    rt.sims["HYD-01"].inject_cooling_degradation(0.4)
    ev = tick_until_event(rt, "COOLING_ANOMALY")
    orc.start(ev["event_id"])
    orc.decide(ev["event_id"], "kim.operator", "APPROVED", 0.8)
    run_until_settled(rt, orc, ev["event_id"])
    g = golden_questions("HYD-01", ev["event_id"], run_id=rt.run_id, until=ev["window_end"])
    assert g["Q1"]["sensor_state"] == "VALID" and g["Q1"]["sustained_anomaly"] is True
    assert g["Q2"]["sop"][0]["doc_id"] == "SOP-COOL-001" and g["Q2"]["sop"][0]["version"] == 2
    assert "REDUCE_LOAD" in g["Q2"]["allowed_actions"]
    assert g["Q3"]["approver"] == "kim.operator" and g["Q3"]["recovered"] is True and g["Q3"]["citations"]
