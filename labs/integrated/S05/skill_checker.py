"""S05 · SKILL.md 점검기 (제공 코드 — 수정하지 않는다).

실제 에이전트가 쓰는 로더(hydops/b7_agent/skill_loader.py)로 읽은 뒤, 필수 절·순서·중단 규칙 문구를 검사한다.
사용: PYTHONPATH=. .venv/bin/python ../labs/integrated/S05/skill_checker.py [skills 폴더]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from hydops.b7_agent.skill_loader import MAX_CHARS, build_system_prompt, load_skill

SKILL_NAME = "hydraulic-cooling-response"
REQUIRED_TOOLS = ["get_asset_context", "get_recent_window", "search_sop", "propose_action"]
REQUIRED_SECTIONS = ["판단 순서", "인용 규칙", "중단 규칙", "결과 형식"]
# 판단 순서 1~4단계에서 부를 도구 (순서가 중요하다: 센서 품질 → 설비 → SOP → 제안 검사)
STEP_TOOLS = {1: "get_recent_window", 2: "get_asset_context", 3: "search_sop", 4: "propose_action"}
# SKILL.md 에 특정 문서의 절 번호를 박아 넣으면 LLM 이 검색되지 않은 절을 인용한다 (교재 I05 흔한 실수)
PINNED_CITATION = re.compile(r"SOP-[A-Z]+-\d{3}[^\n§]{0,12}§\s*\d")


def sections(body: str) -> dict[str, str]:
    out, cur = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return out


def steps(text: str) -> dict[int, str]:
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^(\d+)\.\s", line)
        if m:
            cur = int(m.group(1))
            out[cur] = line
        elif cur is not None:
            out[cur] += "\n" + line
    return out


def check_skill(skills_dir: Path) -> list[str]:
    problems: list[str] = []
    raw = (skills_dir / SKILL_NAME / "SKILL.md").read_text()
    if "____" in raw:
        problems.append(f"빈칸 ____ 이 {raw.count('____')}곳 남아 있다")
    sk = load_skill(SKILL_NAME, skills_dir)
    meta, body = sk["meta"], sk["body"]
    if meta.get("name") != SKILL_NAME:
        problems.append("frontmatter name 이 hydraulic-cooling-response 가 아니다")
    if sorted(meta.get("tools") or []) != sorted(REQUIRED_TOOLS):
        problems.append(f"frontmatter tools 는 {REQUIRED_TOOLS} 네 개여야 한다: {meta.get('tools')}")
    if len(body) >= MAX_CHARS:
        problems.append(f"본문이 {MAX_CHARS}자를 넘어 로더가 뒷부분을 자른다")

    sec = sections(body)
    for name in REQUIRED_SECTIONS:
        if name not in sec:
            problems.append(f"'## {name}' 절이 없다")
    order = steps(sec.get("판단 순서", ""))
    if sorted(order) != list(range(1, 8)):
        problems.append(f"판단 순서는 1~7단계여야 한다: {sorted(order)}")
    for n, tool in STEP_TOOLS.items():
        if tool not in order.get(n, ""):
            problems.append(f"판단 순서 {n}단계에서 `{tool}` 을 불러야 한다")
    s1 = order.get(1, "")
    if not ("SENSOR_FAULT" in s1 and "SENSOR_CHECK" in s1):
        problems.append("1단계: sensor_state 가 SENSOR_FAULT 이면 결정은 SENSOR_CHECK 여야 한다")
    if "승인하지 않는다" not in order.get(5, ""):
        problems.append("5단계: 에이전트는 승인하지 않는다는 문장이 있어야 한다")

    cite = sec.get("인용 규칙", "")
    if not all(k in cite for k in ("`doc_id`", "`version`", "`section`")):
        problems.append("인용 규칙: doc_id·version·section 세 가지를 인용해야 한다")
    if not re.search(r"Skill 은\s*지침.*SOP 가\s*근거", cite):
        problems.append("인용 규칙: Skill 은 지침, SOP 는 근거라는 구분이 있어야 한다")

    stop = sec.get("중단 규칙", "")
    if "`HOLD` (근거 없음 보류)" not in stop:
        problems.append("중단 규칙: 적용 SOP·검색 결과가 없으면 결정은 HOLD 여야 한다")
    if "default_value" not in stop:
        problems.append("중단 규칙: 조치 값은 get_asset_context 의 default_value 를 써야 한다")
    if not re.search(r"SENSOR_FAULT.*결정은 `SENSOR_CHECK`", stop):
        problems.append("중단 규칙: SENSOR_FAULT 사건의 결정은 SENSOR_CHECK 여야 한다")

    pinned = PINNED_CITATION.findall(body)
    if pinned:
        problems.append(f"특정 SOP 절 번호를 박아 넣었다 {pinned} — '검색 결과에 있는 절만 인용'으로 쓴다")

    prompt = build_system_prompt([SKILL_NAME], skills_dir)
    if "[할당된 스킬 가이드]" not in prompt:
        problems.append("시스템 프롬프트에 [할당된 스킬 가이드] 섹션이 없다")
    return problems


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "skills"
    ps = check_skill(d)
    print("통과" if not ps else "\n".join(f"- {p}" for p in ps))
