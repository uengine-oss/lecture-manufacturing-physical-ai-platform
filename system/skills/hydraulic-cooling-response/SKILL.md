---
name: hydraulic-cooling-response
description: 유압설비 냉각 이상·센서 오류 사건에 대해 근거 있는 조치 제안을 만드는 업무 지침 (교육용)
version: 1
tools: [get_asset_context, get_recent_window, search_sop, propose_action]
---
# 유압설비 냉각 이상 대응 Skill

이 Skill 은 **판단 순서와 중단 규칙**만 담는다. 실제 근거는 SOP 검색 결과에서, 실제 실행은 도구에서 나온다.
이 문서에 승인 규칙을 적었다고 승인 검사가 되는 것은 아니다 — 승인 검사는 조치 도구의 코드가 한다.

## 판단 순서
1. **센서 품질 확인** — `get_recent_window(asset_id, 60, event_id)` 으로 (사건 ID 를 주면 탐지 시점 기준으로 고정된다) TS1 의 `sensor_state` 와 품질 플래그를 본다.
   - `sensor_state` 가 `SENSOR_FAULT` 이면(최근 15초 기준) 설비 조치를 제안하지 않는다. 결정은 `SENSOR_CHECK`.
   - `quality_issue_earlier_in_window` 가 true 이면 앞선 센서 문제는 이미 끝났다는 뜻이다. 사건 유형과 지속 이상 여부로 판단을 이어가고, 제안 이유에 한 줄 적는다.
2. **대상 설비 확인** — `get_asset_context(asset_id)` 로 센서·적용 SOP·허용 조치를 확인한다.
3. **SOP 검색** — `search_sop(asset_id, event_type)` 로 적용 SOP 의 절을 찾는다. 허용 조치 절(§4)이 없으면 한 번 더 검색한다.
4. **제안** — 허용 조치 중 하나를 고르고 `propose_action(event_id, action_id, value, citations)` 으로 허용 범위를 검사한다.
5. **승인 확인** — 너는 승인하지 않는다. 제안은 사람 승인 태스크로 넘어간다.
6. **실행** — 승인 기록이 생긴 뒤 조치 도구가 실행한다. 너는 실행 도구를 부르지 않는다.
7. **재측정** — 조치 후 새 관측으로 회복 여부를 판정한다. 명령 성공만으로 종결을 제안하지 않는다.

## 인용 규칙
- 모든 제안에는 검색 결과에 **실제로 나온** `doc_id`, `version`, `section` 을 인용한다.
- 가능하면 **발동 조건** 절과 **허용 조치** 절을 함께 인용한다. 인용하려는 절이 `hits` 에 없으면 `query` 를 바꿔(예: "허용 조치 부하 감소") 다시 검색하고, 그래도 없으면 그 절은 인용하지 않는다.
- 인용 직전에 각 인용이 이번 검색 결과 `hits` 에 그대로 있는지 확인한다. 기억이나 추측으로 절 번호를 쓰지 않는다.
- 이 Skill 문서 자체는 근거로 인용하지 않는다. Skill 은 지침이고 SOP 가 근거다.
- 검색 결과에 없는 문서·절을 지어내지 않는다.

## 중단 규칙
- 적용 SOP 가 없거나 검색 결과에 해당 설비의 절이 없으면 결정은 `HOLD` (근거 없음 보류).
- `propose_action` 검사에서 하나라도 실패하면 결정은 `HOLD` 또는 이미 실행된 경우 `ESCALATE`.
- 원시 센서 배열로 고장을 추정하지 않는다. 도구가 계산한 요약만 사용한다.
- 조치 값은 SOP 에 적힌 기본값(`get_asset_context` 의 `default_value`)을 쓴다.
- 사건 유형이 `SENSOR_FAULT` 이면 `search_sop(asset_id, "SENSOR_FAULT")` 로 센서 점검 SOP 를 찾아 인용하고 결정은 `SENSOR_CHECK` 이다.

## 결과 형식
decision(PROPOSE / HOLD / SENSOR_CHECK / ESCALATE), action_id, value, citations[], rationale(한국어 3문장 이내), checks_passed.
