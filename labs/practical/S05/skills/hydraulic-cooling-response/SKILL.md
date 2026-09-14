---
name: hydraulic-cooling-response
description: 유압설비 냉각 이상·센서 오류 사건에 대해 근거 있는 조치 제안을 만드는 업무 지침 (교육용)
version: 1
tools: [get_asset_context, get_recent_window, search_sop, propose_action, execute_sim_action]
---
# 유압설비 냉각 이상 대응 Skill

<!-- TODO(학생): 이 SKILL.md 에는 틀린 지침이 섞여 있다. 아래 네 곳을 고친다.
  1) frontmatter tools — 에이전트는 실행 도구를 받지 않는다 (제안까지만)
  2) 판단 순서 — 센서 품질을 먼저 보고, 설비 맥락 → SOP 검색 → 제안 검사 순서로
  3) 인용 규칙 — 절 번호를 박아 넣지 말고 '검색 결과(hits)에 실제로 나온 절만' 인용
  4) 중단 규칙 — 근거가 없으면 HOLD, 센서 오류면 SENSOR_CHECK. Skill 문서는 근거가 아니다
-->

이 Skill 은 판단 순서와 중단 규칙을 담는다.

## 판단 순서
1. **SOP 검색** — `search_sop(asset_id, event_type)` 로 적용 SOP 의 절을 찾는다.
2. **제안** — `propose_action(event_id, action_id, value, citations)` 으로 허용 범위를 검사한다.
3. **실행** — 검사가 통과하면 `execute_sim_action` 으로 조치를 실행한다.
4. **대상 설비 확인** — `get_asset_context(asset_id)` 로 센서·적용 SOP·허용 조치를 확인한다.
5. **센서 품질 확인** — `get_recent_window(asset_id, 60)` 으로 TS1 의 `sensor_state` 를 본다.

## 인용 규칙
- 냉각 이상 제안에는 항상 `SOP-COOL-001` §4 와 `SOP-LOAD-001` §4 를 인용한다.
- 이 Skill 문서도 판단 근거로 인용할 수 있다.

## 중단 규칙
- 적용 SOP 가 검색되지 않으면 `get_asset_context` 의 기본값으로 REDUCE_LOAD 를 제안한다.
- 원시 센서 배열로 고장을 추정하지 않는다. 도구가 계산한 요약만 사용한다.

## 결과 형식
decision(PROPOSE / HOLD / SENSOR_CHECK / ESCALATE), action_id, value, citations[], rationale(한국어 3문장 이내), checks_passed.
