"""S06 · 이벤트 → 상태 조회 → SOP 검색 → 제안 검사 연결 — 빈칸 ____ 을 채운다.

hydops/b7_agent/agent.py 의 run_offline_agent 와 같은 순서를 따른다 (Skill 판단 순서 1~4단계).
tools 는 이름 → 함수 사전이다: get_recent_window, get_asset_context, search_sop, propose_action.
이 함수에는 승인·실행 도구가 없다 — 제안까지만 만든다.
"""

____ = "____"  # 빈칸 표시


def cite(hit: dict) -> dict:
    return {"doc_id": hit["doc_id"], "version": hit["version"], "section": hit["section"]}


def proposal(decision, action_id=None, value=None, citations=None, rationale=""):
    return {"decision": decision, "action_id": action_id, "value": value, "citations": citations or [], "rationale": rationale}


def run_lab_agent(ev: dict, tools: dict) -> dict:
    a, et = ev["asset_id"], ev["event_type"]

    # ① 센서 품질 먼저: 최근 60초 요약 (원시 배열이 아니라 코드가 계산한 요약)
    win = tools["____"](asset_id=a, seconds=60)
    ts = win["sensors"].get("TS1", {})
    if et == "SENSOR_FAULT" or ts.get("sensor_state") == "____":
        sop = tools["search_sop"](asset_id=a, event_type="____")
        cits = [cite(h) for h in sop["hits"][:2]]
        if not cits:
            return proposal("HOLD", rationale="센서 오류 SOP 근거가 없어 보류한다.")
        return proposal("____", "SENSOR_CHECK", None, cits, "센서 품질 불량으로 설비 조치를 보류하고 센서 점검을 제안한다.")

    # ② 대상 설비의 적용 SOP·허용 조치 → ③ 그 설비·사건 유형의 SOP 절 검색
    ctx = tools["____"](asset_id=a)
    sop = tools["____"](asset_id=a, event_type=____)
    equipment = [x for x in ctx.get("allowed_actions", []) if x.get("requires_approval") and x.get("default_value") is not None]
    if not sop["hits"] or not equipment:
        return proposal("____", rationale="적용 SOP 근거나 허용 조치가 없어 보류한다.")

    # ④ 허용 조치의 기본값으로 제안 검사 — 실행하지 않는다
    act = equipment[0]
    cits = [cite(h) for h in sop["hits"][:3]]
    chk = tools["____"](event_id=ev["event_id"], action_id=act["action_id"], value=act["____"], citations=cits)
    if not chk["ok"]:
        failed = [c["check"] for c in chk["checks"] if not c["ok"]]
        return proposal("ESCALATE" if "not_already_executed" in failed else "HOLD", act["action_id"], act["default_value"], cits, f"허용 범위 검사 실패: {failed}")
    return proposal("PROPOSE", act["action_id"], act["default_value"], cits, "적용 SOP 가 허용한 조치를 제안한다. 승인 전에는 실행하지 않는다.")
