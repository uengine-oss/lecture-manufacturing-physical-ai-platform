# 통합반 S05 · SOP 검색 필터와 Skill 작성 (교재 I05 §7)

빈칸 `____` 을 채운다. Neo4j·OpenAI 없이 돈다(실제 `search_sop`·`verify_citations`·`skill_loader` 코드 + SOP 마크다운 메모리 사본).

| 파일 | 채울 곳 |
|---|---|
| `evidence.py` | `build_sop_filter`(`asset_scope $like |설비|`, `status $eq active`) / `retrieved_keys`(절 필드·검색 도구 이름) / `decide_after_citation_check`(보류 결정) |
| `skills/hydraulic-cooling-response/SKILL.md` | 빈칸 14곳 — 도구 이름·순서, SENSOR_FAULT → SENSOR_CHECK, 승인하지 않는다, 인용 필드, 지침/근거, HOLD, default_value |
| `roles.py` | FORECAST / DETECT / EVIDENCE / GUIDE / TOOL 역할, 사건 경로, Skill 인용 가능 여부 |
| `skill_checker.py` | 제공 — 수정하지 않는다 |

점검 내용
- 필터가 실제 `search_sop` 가 벡터 저장소에 넘기는 필터와 같다 (HYD-01/02/03, 폐기본 포함)
- HYD-01 결과에 SOP-COOL-001 v1·SOP-COOL-002 없음, HYD-03 0건, 그래프 확인이 SOP-SEN-001 을 걸러냄
- `SKILL.md` 가 점검기 통과 (특정 SOP 절 번호를 박아 넣으면 실패)
- 인용 7사례의 결정이 `verify_citations` 와 같다 (검색되지 않은 절·지어낸 문서·버전 불일치·인용 없음 → HOLD)

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python ../labs/integrated/S05/skill_checker.py      # SKILL.md 만 점검
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S05 -q          # 모두 채우면 18 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S05 -q   # 정답본
```
