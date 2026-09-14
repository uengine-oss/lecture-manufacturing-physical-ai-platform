"""세 가지 Golden Question 을 그래프(B4)와 시계열(B3)을 asset_id·event_id 로 결합해 답한다.

1. HYD-01의 최근 온도는 유효한 센서 관측이며 지속 이상인가?
2. 이 설비에 적용되는 최신 냉각 이상 SOP와 허용 조치는 무엇인가?
3. 어떤 근거로 누가 승인했으며 조치 후 새 관측은 회복했는가?
"""
from __future__ import annotations

from hydops.b3_tsdb import store
from hydops.b4_ontology import graph
from hydops.b7_agent.tools import get_recent_window_impl


def q1(asset_id: str, run_id: str | None = None, until=None) -> dict:
    sensors = {s["quantity"]: s for s in graph.asset_sensors(asset_id)}
    code = sensors["temperature"]["code"]  # 그래프에서 온도 센서를 찾고
    win = get_recent_window_impl(asset_id, 60, until=until, run_id=run_id)["sensors"].get(code, {})  # 시계열에서 값을 본다
    return {"sensor": sensors["temperature"]["sensor_id"], "unit": sensors["temperature"]["unit"], "sensor_state": win.get("sensor_state"), "sustained_anomaly": win.get("sustained_anomaly"), "valid_ratio": win.get("quality", {}).get("valid_ratio"), "valid_max": win.get("valid_max")}


def q2(asset_id: str) -> dict:
    sops = graph.applicable_sops(asset_id, "COOLING_ANOMALY")
    return {"sop": [{"doc_id": s["doc_id"], "version": s["version"], "effective_date": s["effective_date"]} for s in sops], "allowed_actions": sorted({a["action_id"] for s in sops for a in s["allowed_actions"]})}


def q3(event_id: str) -> dict:
    tr = store.event_trace(event_id)
    ev_graph = graph.event_evidence(event_id) or {}
    apr = next((a for a in tr["approvals"] if a["decision"] == "APPROVED"), None)
    ver = tr["verifications"][-1] if tr["verifications"] else None
    return {
        "citations": [c for c in ev_graph.get("citations", []) if c.get("doc_id")],
        "approver": apr["approver"] if apr else None,
        "approved_value": apr["approved_value"] if apr else None,
        "command_status": tr["actions"][0]["command_status"] if tr["actions"] else None,
        "verification": ver["outcome"] if ver else None,
        "recovered": bool(ver and ver["outcome"] == "RECOVERED"),
    }


def golden_questions(asset_id: str, event_id: str, run_id: str | None = None, until=None) -> dict:
    return {"Q1": q1(asset_id, run_id, until), "Q2": q2(asset_id), "Q3": q3(event_id)}
