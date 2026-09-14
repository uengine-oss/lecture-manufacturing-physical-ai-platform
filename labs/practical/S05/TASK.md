# S05 · SOP 검색 필터·근거 검증·SKILL.md 규칙 (실전반 5회)

교재: `textbooks/실전반/P05_SOP와_Skill로_로컬_에이전트_구성.md` §7

## 고칠 파일
| 파일 | 원본 | 틀린 곳 |
|---|---|---|
| `search_lab.py` `build_filter` | `system/hydops/b6_sop/search.py` | `asset_scope` 를 경계 문자 없이 `$like HYD-01` 로 찾음 · `status` 필터 없음 → 폐기본 SOP-COOL-001 v1 이 섞임 |
| `search_lab.py` `confirm_with_graph` | 같은 파일의 그래프 확인 | 벡터 후보를 그대로 자름 → `APPLIES_TO` 가 없거나 사건 유형이 다른 절(SOP-SEN-001)이 근거가 됨, 같은 절 중복 |
| `search_lab.py` `verify_citations_lab` | `system/hydops/b7_agent/agent.py` `verify_citations` | `doc_id` 만 비교 → 검색된 적 없는 v1 §4 인용이 통과 · 인용 0개 제안을 보류하지 않음 |
| `skills/hydraulic-cooling-response/SKILL.md` | `system/skills/.../SKILL.md` | tools 에 실행 도구 · 판단 순서 거꾸로 · 인용 규칙에 절 번호 고정 · 중단 규칙이 "근거 없으면 REDUCE_LOAD 제안" |

`search_sop_lab`·`neo4j_retrieve`·`offline_proposal` 은 제공 함수다. `offline_proposal` 은 `run_offline_agent` 와 같은 순서(센서 품질 → 설비 맥락 → SOP 검색 → 제안 → 근거 검증)를 DB 사건 없이 따른다.

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S05 -q                 # 시작본: 10 failed, 3 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S05 -q  # 정답본: 13 passed
```

## 규칙
- 테스트는 `HYDOPS_AGENT_MODE=offline` 으로 돈다. OpenAI 를 부르지 않는다.
- 테스트의 벡터 검색은 Neo4jVector 와 같은 필터 의미(`$like`=CONTAINS, `$eq`)를 지키는 오프라인 검색기다. Neo4j 의 SOPSection 은 **읽기만** 한다. 공유 Neo4j 에 오프라인 임베딩·인덱스를 만들지 않는다.
- 교재 활동에서는 `neo4j_retrieve`(실제 Neo4jVector, 강사 환경의 임베딩)로 같은 함수를 돌려 시스템 `search_sop` 결과와 대조한다.

## 개인 설명 과제
(a) HYD-02 검색에 SOP-SEN-001 절이 섞이는 경로(어느 필터가 못 걸렀고 어느 확인이 걸렀나) · (b) `SOP-COOL-001@v1#4` 인용이 HOLD 로 바뀌는 줄 · (c) SKILL.md 에 절 번호를 박아 넣었을 때 생긴 실제 실패(교재 흔한 실수) 중 하나를 설명한다.
