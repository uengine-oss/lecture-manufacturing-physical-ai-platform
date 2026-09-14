"""Skill 로더: 할당된 Skill 의 SKILL.md 본문을 에이전트 시스템 프롬프트에 넣는다.

플랫폼의 업무 에이전트도 같은 방식(할당 목록 → SKILL.md 로드 → '[할당된 스킬 가이드]' 섹션)을 쓴다.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from hydops.config import ROOT

SKILLS_DIR = ROOT / "skills"
MAX_CHARS = 6000


def load_skill(name: str, skills_dir: Path = SKILLS_DIR) -> dict:
    text = (skills_dir / name / "SKILL.md").read_text()
    meta, body = {}, text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    return {"name": meta.get("name", name), "meta": meta, "body": body.strip()[:MAX_CHARS]}


def build_system_prompt(assigned: list[str], skills_dir: Path = SKILLS_DIR) -> str:
    parts = [
        "너는 유압설비 운영 에이전트다. 도구가 계산한 결과와 SOP 검색 결과만 근거로 삼는다.",
        "너에게는 실행 권한과 승인 권한이 없다. 조치는 제안까지만 한다.",
        "",
        "[할당된 스킬 가이드]",
    ]
    for name in assigned:
        sk = load_skill(name, skills_dir)
        parts.append(f"### {sk['name']}\n{sk['body']}")
    return "\n".join(parts)
