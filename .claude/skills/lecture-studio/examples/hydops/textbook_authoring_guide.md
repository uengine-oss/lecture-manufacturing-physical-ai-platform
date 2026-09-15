# 차수별 교재·실습 작성 지침 (작성자용)

이 문서는 교재 작성자(사람·에이전트)가 **사실과 어긋나지 않게** 쓰기 위한 기준이다. 모든 수치·경로·명령은 2026-09-14 실제 실행으로 확인한 것이다. 여기 없는 수치를 지어내지 말고, 필요하면 코드를 읽거나 직접 실행해 확인한다.

## 0. 원천 문서

- 실라버스: `lecture/제조_피지컬AI_플랫폼연계_실라버스_v2.docx` (markdown 변환본: 요청 시 `pandoc ... -t markdown`). 회차별 날짜·원 일정 번호·블록·50분×4 단계·산출물·완료 확인은 **실라버스 문구를 그대로** 쓴다 (아래 §6 표에 옮겨 두었다).
- 완성 시스템: `lecture/system/` — 먼저 `lecture/system/README.md` 를 읽는다.
- 시각 자료: `lecture/materials/` (§4 목록).

## 1. 반의 차이 (반드시 반영)

| | 실전반 4학년 | 통합반 2·3학년 |
|---|---|---|
| 수업량 | 9회 × 4시간 (14:00~18:00) | 10회 × 4시간 (09:00~13:00) |
| 학생이 맡는 일 | **함수·질의·정책 수정과 검증** — 제공 함수의 내부 조건과 데이터 연결을 고친다 | **제공 코드의 매핑·설정·조건 완성** — 질의·조건·매핑의 빈칸을 채운다 |
| 팀 | 3~4명 팀, 개인별로 하나의 질의 또는 실패 분기를 설명 | 데이터 담당 / 관계·문서 담당 / 에이전트·조치 담당, 중간에 역할 교대. 초보자는 템플릿 완성, 경험자는 새 센서 별칭이나 조치 조건 하나 추가 |
| 플랫폼 | 6~9회 | 7~10회 |
| 평가 제외 | — | DB 관리, 전체 백엔드 개발, 플랫폼 설치 |

매 4시간 = 50분 활동 네 번 + 휴식 30분 + 회고 10분. 방학 첫 회차(실전반 5회, 통합반 2회)는 환경 복구를 첫 활동에 포함한다. 학기 마지막 시간(실전반 4회, 통합반 1회)에 코드·데이터·설정 체크포인트를 저장한다.

## 2. 시스템 사실 (인용 가능)

### 주소와 기동
- DB: `docker compose up -d` → PostgreSQL `localhost:55432` (hydops/hydops/hydops), Neo4j `bolt://localhost:57687` · Browser `http://localhost:57474` (neo4j / hydops-lecture)
- Python: `cd lecture/system && PYTHONPATH=. .venv/bin/python ...`
- 서버: `scripts/servers.sh local 4` 또는 `scripts/servers.sh platform 4` → 관제 `http://localhost:8800`, MCP `http://localhost:8800/mcp/`, 교육용 플랫폼 콘솔 `http://localhost:8910/console/`, 게시 앱 `http://localhost:8910/apps/hydops-ops/`
- 플랫폼 준비: `scripts/bootstrap_platform.py --upto datasource|ontology|publish|skill|mcp|agent|process|watch|app` 또는 `--all`
- 테스트: `PYTHONPATH=. .venv/bin/python -m pytest tests -q` (25 passed, 별도 DB hydops_test 사용), 플랫폼 폐루프: `scripts/e2e_platform.py` (5 사례 통과)
- 키: OpenAI 키가 없으면 `HYDOPS_AGENT_MODE=offline` — 같은 Skill 순서를 코드로 따르는 결정적 에이전트

### 블록별 핵심 코드
| 블록 | 파일 · 함수 |
|---|---|
| B1 | `hydops/b1_data/uci.py`: `SENSOR_MAP`, `reduce_to_1s`, `load_reduced`, `cycle_observations(ds, cycle_id, asset_id, replay_start)`, `replay_cycles`, `inject_sensor_errors` · `simulator.py`: `HydraulicSimulator(asset_id, seed)`, `.step()`, `.inject_cooling_degradation(eff)`, `.inject_sensor_fault(kind, seconds)`, `.apply_load(load)`, `.apply_fan_boost(f)`, `.fail_next_command()` · `inspection.py`: `synth_lots` |
| B2 | `hydops/b2_quality/checks.py`: `SensorQualityChecker.check/check_many`, 플래그 `OK/MISSING/GAP/SPIKE/STUCK/OUT_OF_RANGE`, `window_quality`, `classify_window`; 기준 `config.QualityRules` (gap_hold_s=5, stuck_run=8, spike_delta TS1=8°C, 물리 범위) |
| B3 | `sql/01_schema.sql` (run, observation, event, event_history, approval, action_log, verification, inspection) · `hydops/b3_tsdb/store.py`: `init_schema`, `create_run`, `insert_observations`(COPY), `recent_window(asset_id, seconds, sensor_id, run_id, until)`, `create_event`(열린 사건 중복 억제), `transition`, `record_approval`, `insert_action_log`(idempotency_key), `insert_verification`, `event_trace` |
| B4 | `hydops/b4_ontology/graph.py`: `CONSTRAINTS`, `ASSETS`(HYD-01 수랭식, HYD-02 공랭식, HYD-03 신규·SOP 없음), `SENSORS`(TS1/PS1/FS1), `ACTIONS`(REDUCE_LOAD 0.6~1.0 기본 0.8, FAN_BOOST 1.0~1.5 기본 1.3, SENSOR_CHECK, ESCALATE), `seed_graph`(MERGE), 질의 `Q_ASSET_SENSORS`, `Q_APPLICABLE_SOP`, `Q_EVENT_EVIDENCE`, `asset_context`, `upsert_event_ref` · `hydops/golden.py`: `q1/q2/q3`, `golden_questions` |
| B5 | `hydops/b5_detect/detector.py`: `ThresholdDetector.feed`(유효 >60°C 10초 연속 → COOLING_ANOMALY, GAP/STUCK → SENSOR_FAULT), `recent_summary`(LLM 에 줄 요약), `PhaseBaseline.fit`, `detect_cycle_phase(values, baseline, k_sigma=4, min_delta_c=3, sustain_s=10, smooth_s=5)` · `evaluate.py`: `fixed_split`(시드 2026, 기준 244 사이클, 시험 180 = 상태별 60), `evaluate(...)` · `product.py`: `check_lots` · `zeroshot.py`(선택): Chronos-Bolt tiny |
| B6 | `hydops/b6_sop/docs/*.md` (SOP-SEN-001 v1, SOP-COOL-001 v1(폐기)·v2, SOP-COOL-002 v1(HYD-02), SOP-LOAD-001 v1, SOP-VER-001 v1, SOP-ESC-001 v1 — 모두 §1 적용 설비 · §2 발동 조건 · §3 확인할 관측 · §4 허용 조치 · §5 승인 주체 · §6 재점검 기준) · `search.py`: `index_sections`, `search_sop(asset_id, event_type, query, k, include_superseded)` — Neo4jVector 메타데이터 필터(`asset_scope $like |HYD-01|`, `status $eq active`) + 그래프 APPLIES_TO 확인. `HashEmbeddings`(오프라인) |
| Skill | `skills/hydraulic-cooling-response/SKILL.md` (frontmatter name/description/version/tools · 판단 순서 7단계 · 인용 규칙 · 중단 규칙 · 결과 형식) · `hydops/b7_agent/skill_loader.py`: `load_skill`, `build_system_prompt` ("[할당된 스킬 가이드]") |
| B7 | `hydops/b7_agent/tools.py`: LangChain `@tool` 4종 `get_asset_context`, `get_recent_window`, `search_sop`, `propose_action` · `agent.py`: `Proposal`(decision PROPOSE/HOLD/SENSOR_CHECK/ESCALATE, action_id, value, citations, rationale), `run_llm_agent`(create_agent + response_format), `run_offline_agent`, `verify_citations`(검색되지 않은 인용 → HOLD), `propose_for_event` |
| B8 | `hydops/b8_action/executor.py`: `propose_action`(검사 목록 event_exists/event_open/action_allowed_by_sop/value_in_range/has_citation/not_already_executed), `execute_sim_action`(오류 코드 APPROVAL_NOT_FOUND, APPROVAL_REJECTED, ACTION_MISMATCH, VALUE_MISMATCH, VALUE_OUT_OF_RANGE, REPEAT_SUPPRESSED, EVENT_NOT_EXECUTABLE), `verify_window`, `verify_recovery` · `service.py`: `gather_evidence`, `record_decision`, `execute`, `verify` · `workflow.py`: LangGraph 노드 evidence → approval(interrupt) → execute → wait_remeasure(interrupt) → verify, `Orchestrator.start/decide/poll`, PostgresSaver(thread_id=event_id) |
| B9 | `hydops/b9_dashboard/app.py` (API: `/api/state`, `/api/control`, `/api/sim/{asset}/inject`, `/api/assets`, `/api/series`, `/api/events`, `/api/events/{id}`, `/api/events/{id}/decision`, `/api/sensors/{sensor_id}/aliases`, `/api/ingest/{asset}`, `/api/system/...`) · `static/index.html` + `app.js` (Vue 3) |
| MCP | `hydops/mcp_tools.py`: 6 도구 (위 4종 + `execute_sim_action`, `verify_recovery`), streamable HTTP `/mcp/` |

### 교육용 플랫폼 (`labplatform/`)
| 모듈 | 핵심 API | 실제 플랫폼 대응 |
|---|---|---|
| Data Fabric `fabric.py` | `POST /fabric/datasources` {name, engine:"postgres", parameters}, `POST /fabric/datasources/{name}/extract-metadata`, `POST .../query` (읽기 전용) — 사전 등록명 `hydops_edu`, 계정 `lab_reader`(SELECT 전용) | Data Fabric 데이터소스 |
| Ontology Studio `studio.py` | `POST /studio/schemas/import`, `PUT .../classes`, `PUT .../relationships`, `PUT .../classes/{c}/binding` {kind: graph(label) \| virtual(datasource, table, column_map, order_by)}, `PUT .../behaviors/{b}`, `GET .../validate`, `POST .../publish`(→ Neo4j `_OntologyModel/_OntologyClass/_OntologyProperty`), `POST .../objects/{c}/fetch`(발행 전 409), `GET .../objects/{c}/{key}/related/{rel}`, `POST .../behaviors/{b}/invoke`, `POST .../golden` | Ontology Studio 클래스·관계·Behavior 발행 |
| Agents `agents.py` | `POST /agents/skills` {files:{"SKILL.md"}}, `POST /agents/mcp-servers` {name, type:"http", url} (명령 기반 설정 거부), `GET .../tools`, `POST .../call`, `POST /agents` {agent_id, skills, mcp_servers, allowed_tools}, `POST /agents/{id}/run`, `POST /agents/watch` {sql, condition:"rows > 0", process_def_id, param_map}, `POST /agents/watch/{id}/tick` | Process GPT 업무 에이전트 · Ontologic Watch Agent |
| Process `process.py` | `POST /process/definitions`, `POST .../{def_id}/start` {values} (인스턴스 키 `def:event_id:회차` 로 중복 시작 거부), `GET /process/instances/{id}`, `GET /process/worklist`, `POST /process/workitems/{id}/complete` (재완료 409) · 템플릿 `templates/process_cooling_response.json`: 사건 접수(폼) → 사건-업무 대응 기록 → 근거 확인·조치 제안(에이전트) → 근거 검증·기록 → 조치 승인(사람, 설비 담당자) → 승인 기록 → 승인 조치 실행(도구) → 조치 후 재점검(도구, 재시도) → 종결/이관/재측정 보류/미실행 종료/보류 | Process GPT 프로세스 · 워크리스트 |
| Apps `apps.py` | `POST /apps` {name, template:"ops-console", config:{hydops_api, platform_api, schema_name, process_def_id}} → 검증 → 번들 → 상태 확인 → 게시 로그 | 아이나루 앱 게시 |
| 템플릿 | `templates/ontology_hydraulic.json` (클래스 9: Asset·Sensor·SOP·Action=graph / Observation·Event·Approval·ActionLog·Verification=virtual, 관계 8, Behavior `Asset.recent_state`, Golden Question 3), `agent_ops.json`, `watch_events.json` | |

### 확인된 수치 (그대로 인용 가능)
- UCI: 2,205 사이클 × 60초. 안정 상태 평균 온도 — 냉각기 100% 36.02°C (489), 20% 44.75°C (480), 3% 56.19°C (480).
- 오류 주입본(사이클 #1500): OK 49 · SPIKE 1 · MISSING 4 · GAP 3 · STUCK 3. **고착은 같은 값 8번째부터 STUCK** 이라 10초 고착 중 3초만 플래그된다(스트리밍 판정의 지연 — 토론 거리).
- B5 평가(고정 시험 구간, 5초 평활): 허용 한계 4σ·최소 3°C → TP 120 · FP 1 · FN 0 · TN 59 / 2σ·최소 1°C → FP 4. **지속 1초와 10초는 FP 가 같고 지연만 0 → 9초** (σ≈0.3 이라 실제 한계는 최소 차이). 지속 조건의 효과는 임계값 근처 떨림에서 보인다: 시뮬레이터 정상 59.8°C 10분 — 경보 신호 지속 1초 99회 · 3초 5회 · 5초 0회 · 10초 0회 / 실제 60.2°C 초과 — 101 · 60 · 38 · 10회.
- 폐루프(시드 7, 냉각 0.4): 감지 t=43s, 조치 t=58s, 조치 없음 마지막 20초 최저 66.87°C, 조치 후 마지막 20초 최고 54.4°C.
- 재측정 세 갈래: 회복(유효 100%, 55°C 이하 연속 56초) · 미개선(냉각 0.25, 연속 0초) · 데이터 부족(유효 25% → INSUFFICIENT_DATA).
- zero-shot(Chronos-Bolt tiny): 시뮬레이터 주입 t=60 → 예측 이탈 경보 t=64, 규칙 경보 t=82 / UCI 상태별 20사이클 경보 0·0·0 (위상 기준은 2%·100%·100%).
- 실제 LLM(gpt-4.1-mini) 에이전트 도구 호출 예: get_recent_window → get_asset_context → search_sop(→ 한 번 더 search_sop) → propose_action, 약 5~10초.
- 플랫폼 폐루프 5 사례: 정상 회복(CLOSED/RECOVERED) · 승인 거부(REJECTED, 실행 기록 0) · 미개선(ESCALATED/NOT_IMPROVED, 명령 SUCCEEDED) · 허용 범위 이탈 0.4(ESCALATED, 실행 기록 0) · 센서 오류(SENSOR_CHECK). 중복 시작 → `duplicate: true` 기존 인스턴스 반환, 승인 태스크 재완료 → HTTP 409.

### 실제 실행에서 드러난 문제 (「흔한 실수」로 쓰기 좋다)
1. 급등 판정을 최근 5개 **중앙값**과 비교했더니, 냉각이 크게 나빠져 온도가 빠르게 오를 때 모든 값이 SPIKE 로 막혀 사건이 안 생겼다 → **직전 유효값과의 1초 점프** + 3회 연속이면 수준 변화로 인정.
2. SKILL.md 에 "부하 감소 SOP §4 를 인용하라"고 **절 번호를 박아 넣었더니** LLM 이 검색되지 않은 절을 인용 → 코드의 근거 검증이 HOLD 로 막았다 (안전장치는 작동). Skill 에는 절 번호 대신 "검색 결과에 있는 절만 인용"을 쓴다.
3. HYD-02 는 SOP 상 FAN_BOOST 가 정당한데 오프라인 에이전트는 REDUCE_LOAD 만 찾아 HOLD 했다 — LLM 과 결과가 달랐다 → 허용 조치를 그래프에서 읽도록 일반화.
4. 실패한 프로세스 인스턴스가 남긴 **열린 사건**이 "설비·유형당 열린 사건 하나" 규칙에 걸려 새 감지를 막았다 → 시뮬레이터 초기화 시 `RUN_ENDED` 로 닫는다 (회복으로 기록하지 않는다).
5. MCP 도구 인자를 `list[dict]` 로 두었더니 OpenAI 함수 스키마가 거부했다 → `Citation(doc_id, version, section)` 타입을 명시.
6. 플랫폼 프로세스가 API 키를 못 읽어 에이전트 단계가 ERROR → 인스턴스는 FAILED 로 남고 사건은 DETECTED 로 머문다 (실패 분기가 기록으로 남는 것 자체가 확인 포인트).

## 3. 표현 원칙

- 한국어 평서체("~한다"). 실라버스 문체를 따른다. 과장·홍보 문구 금지("혁신적", "강력한").
- **금지된 혼동**: 설비 상태 라벨을 제품 불량이라 부르지 않는다 · 재생 시각을 실제 수집 시각이라 하지 않는다 · 규칙 기반 감지를 zero-shot 모델이라 부르지 않는다 · 관계를 그렸다고 실측 인과가 확인됐다고 쓰지 않는다 · 명령 성공을 회복이라 쓰지 않는다 · 프로세스 완료를 설비 회복이라 쓰지 않는다 · 교육용 플랫폼을 실제 플랫폼이라 부르지 않는다("교육용 플랫폼(Lab Platform)", 대응 기능은 "실제 플랫폼 대응"으로 표기).
- 계층 이름: Data Sources / Ontology / Agents / Orchestration (공식). Ontologic 의 Physical·Domain·Dynamic 은 "관점"으로만 쓰고 계층 이름과 섞지 않는다.
- 코드 인용은 실제 파일에서 발췌하고 경로를 붙인다. 발췌는 짧게(핵심 10~25줄).
- 명령에는 **예상 출력**을 붙이되, 실제로 실행해서 얻은 값만 쓴다.

## 4. 시각 자료 목록 (교재에서 상대 경로로 넣는다)

교재 파일 위치가 `lecture/textbooks/<반>/<파일>.md` 이므로 경로는 `../../materials/...`.

**데이터 그림 `materials/figures/`**
- F01_uci_1s_reduction.png — B1 · 사이클 #100 의 TS1/PS1/FS1 원시 vs 1초 축약
- F02_uci_cooler_states.png — 냉각기 상태별 사이클 온도(평균·5~95%)
- F03_quality_flags.png — B2 · 오류 주입본의 원시/정제 값과 플래그 타임라인
- F04_phase_baseline_residual.png — B5 · 정상 위상 기준과 이동평균 잔차·감지 시점
- F05_detection_eval_compare.png — B5 · 임계값(허용 한계)과 지속 조건이 하는 일: UCI 오탐·지연 격자 + 시뮬레이터 임계값 근처 떨림
- F06_closed_loop_same_seed.png — B8 · 같은 시드 조치 유무 폐루프
- F07_verification_outcomes.png — B8 · 회복/미개선/데이터 부족
- F08_neo4j_asset_graph.png — B4 · 설비·센서·SOP·조치 그래프
- F09_sop_search_filter.png — B6 · 설비·버전 필터별 검색 결과
- F10_zeroshot_vs_rules.png — B5 선택 · Chronos zero-shot vs 규칙·위상 기준

**개념도 `materials/diagrams/`**
- D01_architecture.png — 완성 아키텍처(B1~B9 · 플랫폼 대응 · 재측정 루프 · 연결 키)
- D02_event_path.png — 하나의 사건이 통과하는 경로
- D03_state_flow.png — 상태 흐름과 분기, 합격 목표
- D04_skill_sop_tool.png — Skill/SOP/도구 역할 + 도구 계약 표
- D05_local_vs_platform.png — 로컬 LangGraph vs 교육용 플랫폼, 공유 서비스
- D06_roadmap.png — 두 반의 회차 × 블록 로드맵
- D07_storage.png — 파일/PostgreSQL/Neo4j 저장 분리

**실제 화면 `materials/screenshots/`**
- S01_dashboard_normal.png — 관제 화면 정상 운전(사건 없음)
- S02_dashboard_sensor_fault.png — 센서 결측 → SENSOR_CHECK, SOP-SEN-001 인용
- S03_dashboard_pending_approval.png — 냉각 이상 승인 대기(도구 호출·인용·승인 폼)
- S04_dashboard_closed.png — 승인 후 부하 0.8, 재측정 회복, 종결
- S05_dashboard_escalated.png — 심각한 저하, 명령 성공·미개선 → 이관
- S06_dashboard_hold_no_evidence.png — HYD-03 근거 없음 보류
- S07_neo4j_browser_graph.png — Neo4j Browser 에서 SOP-APPLIES_TO-Asset-HAS_SENSOR 경로
- S08_dashboard_rejected.png — 승인 거부 → 미실행 종료
- S10_platform_home.png — 교육용 플랫폼 콘솔 개요(4계층 카드)
- S11_platform_fabric.png — Data Fabric 데이터소스·메타데이터·읽기 전용 질의
- S12_platform_studio_unpublished.png — 발행 전 객체 조회 거부(409)
- S13_platform_studio_published_golden.png — 발행 v1, Event 객체 조회, Golden Question 3개 통과
- S14_platform_agents_mcp_watch.png — 업무 에이전트·Skill·MCP 도구 조회 호출·Watch 실행
- S15_platform_worklist_approval.png — 조치 승인 태스크 폼(event_id·asset_id·run_id·제안값·근거 참조)
- S16_platform_instance_closed.png — 인스턴스 단계 기록(업무 결과 종결·설비 재측정 RECOVERED)
- S17_platform_apps.png — 앱 게시 로그
- S18_app_ops_console.png — 게시된 제조 운영 앱, 같은 사건 확인 ✔✔✔

그림을 새로 만들 필요가 있으면 `lecture/materials/figures/extra/` 에 matplotlib(폰트 Pretendard)으로 실제 실행 결과를 그려 넣는다. 가짜 스크린샷·가짜 출력은 금지.

## 5. 교재 템플릿 (각 회차 한 파일)

파일명: `textbooks/실전반/P01_첫_데이터가_흐르는_시스템.md` … `P09_…`, `textbooks/통합반/I01_센서와_데이터_흐름_알아보기.md` … `I10_…`

```markdown
# 실전반 1회 · 첫 데이터가 흐르는 시스템

| 날짜·시간 | 2026-10-31 (토) 14:00~18:00 | 모듈 | M1 · 원 일정 3번 |
|---|---|---|---|
| 블록 | 구현 B1 · B2 · B3 | 산출물 | B1→B2→B3 데이터 경로 |
| 완료 확인 | 단위·설비 ID·원본/합성 구분을 포함한 관측 조회 | | |

![이번 회차가 다루는 블록](../../materials/diagrams/D06_roadmap.png)

## 이번 회차에서 할 일
(3~5문장: 시스템 전체에서 이번 회차 블록의 위치, 끝나면 무엇이 동작하는지)

### 학습 목표
- …(3~4개, 확인 가능한 동사)

## 1. 시작 전 준비 (복습·환경 확인)
명령 + 예상 출력

## 2. 핵심 개념
그림 1~3개 + 설명. 오해하기 쉬운 점을 "주의" 인용 블록으로.

## 3. 활동 1 — (실라버스 1단계 문구) · 50분
### 목표 / ### 따라 하기 (단계 번호, 명령·코드) / ### 확인 포인트 (실제 출력) / ### 흔한 실수

## 4. 활동 2 — … · 50분
## 5. 활동 3 — … · 50분
## 6. 활동 4 — … · 50분

## 7. 실습 과제
- 실전반: `labs/practical/S01/` — 수정할 함수와 검증 방법
- 통합반: `labs/integrated/S01/` — 빈칸 위치와 검증 방법
- 확인 명령: `cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/<반>/SXX -q`

## 8. 완료 확인 체크리스트
- [ ] (실라버스 완료 확인 문구를 측정 가능한 항목으로 쪼갠다)

## 9. 회고 (10분)
질문 3개 + (실전반) 개인 설명 과제: "내가 설명할 질의 또는 실패 분기 하나"

## 10. 실제 플랫폼 대응 (해당 회차만)
| 교육용 플랫폼 기능 | 실제 플랫폼 기능 | 다른 점 |

## 강사 노트
시간 배분표, 사전 준비(bootstrap 단계), 장애 대응(플랫폼 장애 시 로컬 어댑터로 계속하되 플랫폼 실습 완료로 기록하지 않고 별도 보충), 체크포인트 저장(해당 회차)

## 용어
```

분량: 회차당 A4 10~18쪽 분량(대략 한국어 6,000~12,000자). 그림은 회차당 최소 3개(데이터 그림·개념도·실제 화면을 섞는다). 표를 적극 쓴다.

## 6. 회차 표 (실라버스 원문)

### 실전반
| 회 | 날짜 | 모듈·원 일정 | 블록 | 네 단계 | 산출물 | 완료 확인 |
|---|---|---|---|---|---|---|
| 1 | 2026-10-31 토 | M1 · 3번 | 구현 B1, B2, B3 | 1. 완성 시스템 시연과 아키텍처 읽기 → 2. 세 센서 CSV를 공통 관측 형식으로 매핑 → 3. 제공 적재 함수를 PostgreSQL에 연결 → 4. 최근 60초를 조회하고 원본 사이클 추적 | B1→B2→B3 데이터 경로 | 단위·설비 ID·원본/합성 구분을 포함한 관측 조회 |
| 2 | 2026-11-07 토 | M1 · 4번 | 확장 B2, B3 | 1. 결측·스파이크·고착 사례 비교 → 2. 품질 기준과 1초 집계 수정 → 3. 원시 값·정제 값·품질 플래그 저장 → 4. 설비 이상과 센서 오류를 다른 상태로 표시 | 품질 검사와 이력 저장 | 긴 결측을 정상 값으로 숨기지 않고 판정 보류 |
| 3 | 2026-11-21 토 | M1 · 6번 | 구현 B4 / 확장 B3 | 1. 세 가지 Golden Question과 Asset·Sensor·SOP 관계 정하기 → 2. Resource·Measure 대응을 읽고 제공 MERGE 문으로 적재 → 3. 파라미터 Cypher로 설비에서 SOP까지 탐색 → 4. asset_id로 그래프와 시계열 결과를 결합 | B3+B4 설비 맥락 조회 | 다른 설비의 SOP가 섞이지 않는 관계 질의 |
| 4 | 2026-11-28 토 | M2 · 7번 | 구현 B5, B9 / 확장 B2, B3 | 1. 정상 위상 기준과 이동 통계 적용 → 2. 지속 조건과 이벤트 중복 억제 → 3. 이벤트를 저장하고 제공 화면에 표시 → 4. 오탐 평가 또는 제로샷 예측 비교 후 체크포인트 저장 | B1→B2→B3→B5→B9 감지 시스템 | 단발 오류와 지속 이상을 구분하고 시험 구간 고정 |
| 5 | 2027-01-25 월 | M3 · 8번 | 구현 B6, B7 / 확장 B4 | 1. 환경 복구와 준비된 도구 입출력 확인 → 2. SOP 절 검색과 적용 대상·버전 필터 연결 → 3. SKILL.md의 판단 순서와 인용 규칙 수정 → 4. LangChain 도구로 근거 있는 조치 제안 생성 | B4+B6→B7 근거 기반 제안 | 스킬 지침과 문서 근거를 구분하고 근거 없으면 보류 |
| 6 | 2027-01-26 화 | M3 · 10번 | 확장 B4, B7 / 플랫폼 B3, B4 | 1. Data Fabric에 사전 등록된 교육용 DB 확인 → 2. Ontology Studio에서 제공 클래스 매핑 검토 → 3. 스키마 발행과 설비·최근 상태 질의 → 4. 컨텍스트 조회를 플랫폼 어댑터로 바꾸어 결과 비교 | 플랫폼 EKG를 조회하는 같은 에이전트 | 동일 asset_id로 교육용 조회와 플랫폼 조회를 대조 |
| 7 | 2027-01-27 수 | M3 · 12번 | 구현 B8 / 확장 B6, B7 / 플랫폼 B6, B7, B8 | 1. 업무 에이전트에 교육용 Skill 할당 → 2. 강사 제공 MCP 도구를 등록하고 조회 호출 → 3. 접수→제안→사람 승인→조치→재점검 템플릿 입력 매핑 → 4. 승인 거부·중복 요청·허용 범위 이탈 확인 | 실제 프로세스 인스턴스와 승인 이력 | event_id·asset_id가 입력 폼과 실행 기록에 보존 |
| 8 | 2027-01-28 목 | M4 · 14번 | 확장 B1, B5, B8 | 1. 상태를 가진 시뮬레이터에 냉각 이상 주입 → 2. 플랫폼 승인 후 부하 감소 도구 실행 → 3. 새 관측으로 회복 또는 미개선 판단 → 4. 실패 분기 검증 또는 제공 Watch Agent 사건 조회 실습 | B8→B1→B2→B3→B5 재측정 루프 | 명령 성공과 실제 관측 회복을 별도로 판정 |
| 9 | 2027-01-29 금 | M4 · 16번 | 확장 B9 / 플랫폼 B9 | 1. 제공 Vue 화면을 설비·이벤트 조회에 바인딩 → 2. 선택 이벤트에서 Process GPT 업무 열기 → 3. 준비된 배포 환경에 게시하고 로그 확인 → 4. 새 센서 별칭 매핑과 폐루프 최종 시연 | 우리 플랫폼에서 사용하는 제조 운영 앱 | 화면·프로세스·조치 기록이 같은 사건을 가리킴 |

### 통합반
| 회 | 날짜 | 모듈·원 일정 | 블록 | 네 단계 | 산출물 | 완료 확인 |
|---|---|---|---|---|---|---|
| 1 | 2026-11-14 토 | M1 · 5번 | 구현 B1, B2 | 1. 완성 시연과 아키텍처 블록 카드 읽기 → 2. 세 센서 CSV를 제공 노트북으로 열기 → 3. 설비·센서·단위 매핑 표 채우기 → 4. 재생 버튼으로 그래프 확인하고 저장본 남기기 | B1→B2 데이터 읽기 | 값 하나의 설비·센서·단위·출처를 설명 |
| 2 | 2027-01-25 월 | M1 · 9번 | 구현 B3 / 확장 B2 | 1. 환경 복구와 첫 시간 복습 → 2. 오류 주입본의 결측·급등·고착 찾기 → 3. 제공 함수로 품질 검사와 DB 적재 → 4. 조회 조건을 바꿔 정상·보류 구간 비교 | B1→B2→B3 저장과 조회 | 센서 오류를 곧바로 설비 고장으로 해석하지 않음 |
| 3 | 2027-01-26 화 | M1 · 11번 | 구현 B4 | 1. 세 가지 질문에 필요한 설비·센서·SOP 관계 맞추기 → 2. 제공 그래프 적재 문장의 ID 수정 → 3. 세 가지 Cypher 질의의 빈칸 채우기 → 4. 관계 결과에 최근 센서 값을 연결 | B3+B4 관계가 있는 데이터 | 대상 설비의 센서와 SOP를 찾는 질의 실행 |
| 4 | 2027-01-27 수 | M2 · 13번 | 구현 B5, B9 / 확장 B2, B3 | 1. 이동 통계 그래프와 정상 위상 비교 → 2. 지속 조건을 바꿔 오탐 관찰 → 3. 센서 오류·설비 이상·합성 제품 품질 이벤트 구분 → 4. 제공 화면에 경보를 붙이고 평가 | B5→B9 탐지 결과 표시 | 제품 불량과 설비 상태 라벨을 구분 |
| 5 | 2027-01-28 목 | M3 · 15번 | 구현 B6 / 확장 B4 | 1. SOP 다섯 문서와 검색 결과 읽기 → 2. 설비·버전 검색 필터 수정 → 3. 제공 SKILL.md의 조건·순서·중단 규칙 채우기 → 4. 근거 없는 질문 보류 확인과 제로샷 예측 짧은 시연 | B4→B6 문서 근거와 작업 지침 | 예측·이상감지·작업 지침의 역할을 설명 |
| 6 | 2027-01-29 금 | M3 · 17번 | 구현 B7, B8 | 1. 제공 LangChain 도구 입력과 결과 읽기 → 2. 이벤트→상태 조회→SOP 검색 연결 → 3. 모의 승인 버튼과 부하 감소 도구 연결 → 4. 거부·실패·재조회 흐름을 제공 상태표로 확인 | B7→B8 로컬 조치 흐름 | 도구와 Skill이 다른 역할임을 설명하고 승인 전 미실행 |
| 7 | 2027-02-01 월 | M3 · 18번 | 확장 B4 / 플랫폼 B3, B4 | 1. 플랫폼 데이터소스와 기존 클래스 찾기 → 2. 준비된 클래스·관계 매핑 확인 → 3. 수업용 스키마 발행과 객체 조회 → 4. 같은 설비를 로컬·플랫폼 화면에서 대조 | 플랫폼에 연결된 설비 맥락 | 발행과 데이터 존재를 구분하고 실제 조회 결과 확인 |
| 8 | 2027-02-02 화 | M3 · 19번 | 확장 B6, B7, B8 / 플랫폼 B6, B7, B8 | 1. 사전 등록된 Skill을 업무 에이전트에 할당 → 2. 제공 도구 목록에서 상태·검색·조치 도구 확인 → 3. 프로세스 템플릿에 이벤트 입력 매핑 → 4. 사람 승인과 거부 결과를 업무 화면에서 확인 | 플랫폼 업무 인스턴스와 승인 기록 | 학생별 새 에이전트 프레임워크 개발 없이 기능 연결 |
| 9 | 2027-02-03 수 | M4 · 20번 | 확장 B9 / 플랫폼 B9 | 1. 제공 화면의 설비·이벤트 데이터 연결 → 2. 선택 사건의 업무 시작·상태 조회 버튼 연결 → 3. 준비된 서버에 게시하고 앱 URL 확인 → 4. 시뮬레이터 조치·재조회와 재시작 연습 | 플랫폼에서 여는 교육용 앱 | 앱 URL에서 같은 사건의 데이터와 업무 진행을 조회 |
| 10 | 2027-02-04 목 | M4 · 21번 | 확장 B1, B5, B8, B9 | 1. 정상·센서 오류·설비 이상 시연 → 2. 근거 확인과 승인 조치 → 3. 재측정 회복·미개선·중복 요청 검증 → 4. 완성 아키텍처 설명과 개인 역할 발표 | B1~B9 연결과 플랫폼 폐루프 | 같은 event_id의 감지·근거·조치·재측정 기록 제출 |

M1 데이터와 온톨로지 · M2 감지와 평가 · M3 근거·에이전트·플랫폼 연결 · M4 폐루프와 운영.

## 7. 실습(labs) 규칙

```
lecture/labs/<practical|integrated>/SXX/
├─ TASK.md            과제 설명 (교재 §7 과 같은 내용을 짧게)
├─ <starter files>    실전반: 동작하지만 조건이 틀리거나 비어 있는 함수(# TODO(학생) 표시) / 통합반: ____ 빈칸
├─ solution/          같은 파일의 정답본
└─ test_check.py      pytest — 기본은 학생 파일을 검사, LAB_SOLUTION=1 이면 solution/ 을 검사
```

- 테스트 실행: `cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/<반>/SXX -q` · 정답 검증: `LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/<반>/SXX -q` → **반드시 통과해야 한다.** 학생 시작본은 실패해야 한다(단, 읽기 과제만 있는 회차는 예외).
- 학생 파일 import 는 `test_check.py` 에서 `LAB_SOLUTION` 에 따라 경로를 골라 `importlib` 로 불러온다.
- `lecture/system/` 의 코드는 **수정하지 않는다** (읽기·import 만). 필요한 코드는 lab 폴더로 복사해 변형한다.
- 공유 환경을 깨지 않는다: `store.init_schema(reset=True)`, `graph.reset_graph()`, `labplatform.db.reset()`, `scripts/servers.sh`, `/api/control` reset, 테이블 TRUNCATE 금지. DB 에 쓰는 테스트는 run_id 를 `LAB-` 로 시작하게 하고 끝나면 자기 행만 지운다(ON DELETE 순서 주의: verification → action_log → approval → event_history → event → observation → run).
- Neo4j 에 쓰는 테스트는 기존 시드와 **같은 값**을 MERGE 하거나 `Lab` 접두사 라벨을 쓰고 끝나면 지운다.
- 플랫폼 회차 테스트: 학생 산출물(JSON 매핑·SKILL.md·폼 매핑·앱 config)을 정적으로 검사하고, 플랫폼 서버(:8910)는 GET 과 `validate` 류만 호출한다. 스키마를 발행해 보는 테스트는 `schema_name` 을 `Lab_` 로 시작하게 한다. 프로세스 인스턴스 시작·시뮬레이터 주입은 테스트에서 하지 않는다(교재 활동에서 손으로 한다).
- LLM 호출이 필요한 테스트는 `HYDOPS_AGENT_MODE=offline` 으로도 통과하게 쓴다.
