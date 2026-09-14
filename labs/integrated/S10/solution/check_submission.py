"""통합반 10회 — 같은 event_id 의 감지·근거·조치·재측정 기록 제출 검사기.

사용 (lecture/system 에서):
  PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py EVT-...        # 한 사건
  PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py --all          # 전체 실행 회차의 사건
  PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py EVT-... --md   # 제출 기록 초안(Markdown)

실라버스 합격 목표(교육용 시험 사례의 목표)를 기록으로 확인한다.
  근거 없는 조치 0건 · 승인 없는 실행 0건 · 중복 실행 0건 · 재측정 없는 회복 판정 0건
이 스크립트는 GET 만 호출한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

import httpx

____ = None  # 빈칸 표시

HYDOPS_API = "http://localhost:8800"
MAX_SUCCEEDED_ACTIONS = 1     # 같은 사건에서 성공한 조치의 최대 개수 (hydops/config.py max_action_attempts)
APPROVED = "APPROVED"         # 실행을 허락하는 승인 결정값
RECOVERED = "RECOVERED"       # 회복으로 인정하는 재측정 판정값
CLOSED = "CLOSED"             # 재측정 회복 후의 사건 상태
CLOSER = "verifier"           # CLOSED 로 바꿀 수 있는 유일한 행위자 (event_history.actor)


def fetch_detail(event_id: str) -> dict:
    r = httpx.get(f"{HYDOPS_API}/api/events/{event_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def list_event_ids(limit: int = 100) -> list[str]:
    return [e["event_id"] for e in httpx.get(f"{HYDOPS_API}/api/events", params={"all_runs": "true", "limit": limit}, timeout=30).json()]


def _t(s) -> datetime:
    return datetime.fromisoformat(str(s).replace(" ", "T"))


def _res(ok: bool, message: str, problems: list[str] | None = None) -> dict:
    return {"ok": ok, "message": message, "problems": problems or []}


def _proposal(d: dict) -> dict:
    return d["event"].get("proposal") or {}


# ---- 규칙 1: 근거 없는 조치 0건 ---------------------------------------------------------
def rule_evidence(d: dict) -> dict:
    if not d["actions"]:
        return _res(True, "실행 기록 없음 — 해당 없음")
    citations = (_proposal(d).get("proposal") or {}).get("citations") or []
    problems = [f"인용 검증 문제: {p}" for p in (_proposal(d).get("citation_problems") or [])]
    if len(citations) == 0:
        problems.append("실행했는데 제안에 SOP 인용이 없다")
    found = {(c["doc_id"], int(c["version"]), str(c["section"])) for c in d.get("citation_texts", []) if c.get("text")}
    for c in citations:
        if (c["doc_id"], int(c["version"]), str(c["section"])) not in found:
            problems.append(f"그래프에 본문이 없는 인용 {c['doc_id']} v{c['version']} §{c['section']}")
    return _res(not problems, f"인용 {len(citations)}개", problems)


# ---- 규칙 2: 승인 없는 실행 0건 ---------------------------------------------------------
def rule_approval(d: dict) -> dict:
    event_id = d["event"]["event_id"]
    approvals = {a["approval_id"]: a for a in d["approvals"]}
    problems = []
    for a in d["actions"]:
        apr = approvals.get(a["approval_id"])
        if apr is None:
            problems.append(f"{a['action_log_id']}: 승인 기록 없이 실행")
            continue
        if apr["decision"] != APPROVED:
            problems.append(f"{a['action_log_id']}: 승인 결정이 {apr['decision']}")
        if apr["event_id"] != event_id:
            problems.append(f"{a['action_log_id']}: 다른 사건의 승인 {apr['event_id']}")
        if not _t(apr["decided_at"]) <= _t(a["executed_at"]):
            problems.append(f"{a['action_log_id']}: 실행 시각이 승인 시각보다 앞선다")
        if apr["approved_value"] != a["requested_value"]:
            problems.append(f"{a['action_log_id']}: 승인값 {apr['approved_value']} ≠ 실행값 {a['requested_value']}")
    rejected = [a for a in d["approvals"] if a["decision"] != APPROVED]
    if rejected and d["actions"]:
        problems.append("거부된 사건에 실행 기록이 있다")
    return _res(not problems, f"승인 {len(d['approvals'])}건 · 실행 {len(d['actions'])}건", problems)


# ---- 규칙 3: 중복 실행 0건 -----------------------------------------------------------
def rule_duplicate(d: dict) -> dict:
    keys = [a["idempotency_key"] for a in d["actions"]]
    succeeded = [a for a in d["actions"] if a["command_status"] == "SUCCEEDED"]
    problems = []
    if len(keys) != len(set(keys)):
        problems.append(f"같은 중복 방지 키가 여러 번 기록됐다: {keys}")
    if len(succeeded) > MAX_SUCCEEDED_ACTIONS:
        problems.append(f"성공한 조치 {len(succeeded)}건 > 허용 {MAX_SUCCEEDED_ACTIONS}건")
    return _res(not problems, f"중복 방지 키 {keys or '없음'}", problems)


# ---- 규칙 4: 재측정 없는 회복 판정 0건 ----------------------------------------------------
def rule_verification(d: dict) -> dict:
    ev = d["event"]
    closed = [h for h in d["history"] if h["to_status"] == CLOSED]
    if ev["status"] != CLOSED and not closed:
        return _res(True, f"종결 아님({ev['status']}) — 해당 없음")
    action_ts = {a["action_log_id"]: a["sim_ts"] for a in d["actions"]}
    good = [
        v for v in d["verifications"]
        if v["outcome"] == RECOVERED and v["action_log_id"] in action_ts and _t(v["window_start"]) >= _t(action_ts[v["action_log_id"]])
    ]
    problems = []
    if len(good) < 1:
        problems.append("CLOSED 인데 조치 이후 창의 RECOVERED 재측정 기록이 없다")
    for h in closed:
        if h["actor"] != CLOSER:
            problems.append(f"CLOSED 전이 행위자가 {h['actor']} (재측정 판정자가 아님)")
    return _res(not problems, f"회복 재측정 {len(good)}건", problems)


RULES = [("근거 없는 조치 0건", rule_evidence), ("승인 없는 실행 0건", rule_approval), ("중복 실행 0건", rule_duplicate), ("재측정 없는 회복 판정 0건", rule_verification)]


def check(d: dict) -> dict:
    results = {name: fn(d) for name, fn in RULES}
    return {"event_id": d["event"]["event_id"], "status": d["event"]["status"], "passed": all(r["ok"] for r in results.values()), "rules": results}


def build_record(d: dict) -> dict:
    """제출 기록: 같은 event_id 의 감지·근거·조치·재측정."""
    ev, prop = d["event"], _proposal(d)
    p = prop.get("proposal") or {}
    ref = ev.get("process_ref") or {}
    return {
        "event_id": ev["event_id"],
        "감지": {"event_id": ev["event_id"], "asset_id": ev["asset_id"], "run_id": ev["run_id"], "event_type": ev["event_type"], "rule_version": ev["rule_version"], "evidence": ev["evidence"], "window": [ev["window_start"], ev["window_end"]]},
        "근거": {"event_id": ev["event_id"], "decision": p.get("decision"), "action_id": p.get("action_id"), "value": p.get("value"), "citations": p.get("citations", []), "tool_calls": [t["tool"] for t in prop.get("tool_trace", [])], "citation_problems": prop.get("citation_problems")},
        "조치": {"event_id": ev["event_id"], "approvals": [{k: a[k] for k in ("approval_id", "event_id", "approver", "decision", "approved_value", "decided_at")} for a in d["approvals"]], "actions": [{k: a[k] for k in ("action_log_id", "event_id", "approval_id", "action_id", "requested_value", "idempotency_key", "command_status", "executed_at")} for a in d["actions"]]},
        "재측정": {"event_id": ev["event_id"], "verifications": [{"verification_id": v["verification_id"], "event_id": v["event_id"], "action_log_id": v["action_log_id"], "outcome": v["outcome"], "window": [v["window_start"], v["window_end"]], "longest_below_s": v["metrics"].get("longest_below_s"), "valid_ratio": v["metrics"].get("valid_ratio")} for v in d["verifications"]]},
        "업무": {"instance_id": ref.get("instance_id"), "key": ref.get("key")},
        "최종 상태": {"status": ev["status"], "status_reason": ev["status_reason"]},
    }


def to_markdown(d: dict) -> str:
    rec, res = build_record(d), check(d)
    lines = [f"# 제출 기록 — {rec['event_id']}", "", f"- 최종 상태: {rec['최종 상태']['status']} ({rec['최종 상태']['status_reason']})", f"- 프로세스 인스턴스: {rec['업무']['instance_id'] or '없음(로컬 처리)'}", ""]
    for sec in ("감지", "근거", "조치", "재측정"):
        lines += [f"## {sec}", "```json", json.dumps(rec[sec], ensure_ascii=False, indent=2, default=str), "```", ""]
    lines += ["## 합격 목표 검사", "| 목표 | 결과 | 설명 |", "|---|---|---|"]
    for name, r in res["rules"].items():
        lines.append(f"| {name} | {'통과' if r['ok'] else '위반'} | {r['message']}{' · ' + '; '.join(r['problems']) if r['problems'] else ''} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ids = list_event_ids() if "--all" in argv else [a for a in argv if not a.startswith("--")]
    if not ids:
        print(__doc__)
        return 2
    failed = 0
    for eid in ids:
        d = fetch_detail(eid)
        if "--md" in argv:
            print(to_markdown(d))
            continue
        res = check(d)
        failed += not res["passed"]
        marks = " ".join(("✔" if r["ok"] else "✘") + name for name, r in res["rules"].items())
        print(f"{res['event_id']} {res['status']:17s} {marks}")
        for r in res["rules"].values():
            for p in r["problems"]:
                print("   -", p)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
