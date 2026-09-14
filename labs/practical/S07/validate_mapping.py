"""S07 · 프로세스 템플릿 입력 매핑 정적 검사기 (제공 코드 — 수정하지 않는다).

검사 기준은 실라버스 'Skill과 조치 프로세스 계약'과 lecture/system/labplatform/process.py 의 동작이다.
- 접수 폼과 조치 승인 태스크를 분리하고, event_id·asset_id·run_id·제안값·근거 참조를 승인 폼에 읽기 전용으로 매핑한다.
- 승인 기록이 만든 approval_id 를 조치 도구 인자로 넘긴다. approved=true 같은 주장은 인자로 넘기지 않는다.
- 조치 도구의 value 는 사람이 승인한 값(approved_value)이다.

사용: python validate_mapping.py [process_cooling_response.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VAR = re.compile(r"\$\{([A-Za-z0-9_]+)(?:\.[A-Za-z0-9_.]+)?\}")
ENGINE_VARS = {"instance_id", "def_id", "instance_key", "HYDOPS_API", "agent_result"}  # process.py 가 넣는 변수
READONLY_CONTEXT = ["event_id", "asset_id", "run_id", "action_id", "proposed_value", "citations"]


def _vars_in(obj) -> set[str]:
    return set(VAR.findall(json.dumps(obj, ensure_ascii=False)))


def validate(defn: dict) -> list[str]:
    problems: list[str] = []
    acts = {a["id"]: a for a in defn["activities"]}
    first = defn["activities"][0]

    # 1) 접수 폼
    if first["type"] != "form":
        problems.append("첫 활동은 접수 폼(type=form)이어야 한다")
    intake = {f["name"]: f for f in first.get("fields", [])}
    for name in ("event_id", "asset_id", "run_id", "event_type"):
        if not intake.get(name, {}).get("required"):
            problems.append(f"접수 폼에 필수 입력 {name} 가 없다")
    if defn.get("instance_key") != "event_id":
        problems.append("instance_key 는 event_id 여야 한다 (인스턴스 키 def:event_id:회차)")

    # 2) 정의되지 않은 변수 참조
    defined = set(intake) | set(defn.get("defaults", {})) | ENGINE_VARS
    for a in defn["activities"]:
        defined |= set(a.get("outputs", {}))
        defined |= {f["name"] for f in a.get("fields", [])}
        ru = a.get("retry_until") or {}
        defined |= set(ru.get("update_vars", {}))
    for a in defn["activities"][1:]:
        body = {k: v for k, v in a.items() if k not in ("id", "name", "type", "outputs", "retry_until")}
        for v in sorted(_vars_in(body) - defined):
            problems.append(f"{a['id']}: 정의되지 않은 변수 ${{{v}}}")

    # 3) 조치 승인 태스크
    apr = acts.get("approve")
    if not apr or apr["type"] != "human" or not apr.get("role"):
        problems.append("approve 는 역할(role)이 있는 사람 태스크(type=human)여야 한다")
    else:
        fields = {f["name"]: f for f in apr["fields"]}
        for name in READONLY_CONTEXT:
            f = fields.get(name)
            if f is None:
                problems.append(f"승인 폼에 {name} 가 없다")
                continue
            if not f.get("readonly"):
                problems.append(f"승인 폼의 {name} 는 readonly 여야 한다 (승인자가 사건 맥락을 바꾸지 못하게)")
            if f.get("default") != f"${{{name}}}":
                problems.append(f"승인 폼의 {name} 기본값은 ${{{name}}} 이어야 한다 (현재 {f.get('default')!r})")
        d = fields.get("decision", {})
        if not d.get("required") or set(d.get("options", [])) != {"APPROVED", "REJECTED"} or d.get("readonly"):
            problems.append("decision 은 APPROVED/REJECTED 중 고르는 편집 가능한 필수 입력이어야 한다")
        if not fields.get("approver", {}).get("required") or fields.get("approver", {}).get("readonly"):
            problems.append("approver 는 편집 가능한 필수 입력이어야 한다")
        av = fields.get("approved_value", {})
        if av.get("readonly") or av.get("default") != "${proposed_value}":
            problems.append("approved_value 는 편집 가능하고 기본값이 ${proposed_value} 여야 한다")

    # 4) 승인 기록 → approval_id
    rec = acts.get("record_decision", {})
    if rec.get("body", {}).get("value") != "${approved_value}":
        problems.append("record_decision body.value 는 ${approved_value} 여야 한다")
    if rec.get("outputs", {}).get("approval_id") != "response.approval.approval_id":
        problems.append("record_decision 은 outputs.approval_id = response.approval.approval_id 를 남겨야 한다")

    # 5) 조치 도구 인자
    act = acts.get("act", {})
    if act.get("tool") != "execute_sim_action":
        problems.append("act 는 execute_sim_action 도구를 호출해야 한다")
    expected = {"event_id": "${event_id}", "approval_id": "${approval_id}", "action_id": "${action_id}", "value": "${approved_value}"}
    if act.get("args") != expected:
        problems.append(f"act.args 는 {expected} 여야 한다 (현재 {act.get('args')})")
    rc = acts.get("recheck", {})
    if rc.get("tool") != "verify_recovery" or rc.get("args", {}).get("action_log_id") != "${action_log_id}" or rc.get("args", {}).get("event_id") != "${event_id}":
        problems.append("recheck 는 verify_recovery(event_id, action_log_id, window_index) 를 호출해야 한다")

    # 6) 전이
    for t in defn["transitions"]:
        if t["from"] not in acts or t["to"] not in acts:
            problems.append(f"전이 {t} 의 활동이 정의에 없다")
    return problems


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "process_cooling_response.json")
    probs = validate(json.loads(path.read_text()))
    print("OK" if not probs else "\n".join(f"- {p}" for p in probs))
    sys.exit(1 if probs else 0)
