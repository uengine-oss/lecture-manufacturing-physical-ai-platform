# HydOps 강의용 완성 시스템

유압설비의 냉각 이상을 발견하고, 설비 관계와 조치 매뉴얼(SOP)을 확인한 뒤, 사람이 승인한 조치를 시뮬레이터에 실행하고 **새 관측으로 회복을 다시 측정**하는 시스템이다. 실라버스 「제조 피지컬 AI 플랫폼 연계」의 B1~B9 블록과 후반부 플랫폼 연결을 모두 구현했다.

> 모든 수치 기준(60°C·10초 경보, 부하 0.8, 55°C·10초 회복)은 **교육용 가정값**이다. UCI 설비의 운전 기준이 아니며, 시뮬레이터와 제품 검사값은 합성 데이터다.

## 1. 구성 한눈에

| 계층 | 블록 | 코드 | 후반부 연결 (교육용 플랫폼) |
|---|---|---|---|
| Data Sources | B1 데이터·시뮬레이터 | `hydops/b1_data/uci.py` · `simulator.py` · `inspection.py` | Data Fabric `labplatform/fabric.py` |
| | B2 품질 검사 | `hydops/b2_quality/checks.py` | |
| | B3 PostgreSQL | `sql/01_schema.sql` · `hydops/b3_tsdb/store.py` | |
| Ontology | B4 Neo4j 설비 관계 | `hydops/b4_ontology/graph.py` · `hydops/golden.py` | Ontology Studio `labplatform/studio.py` |
| | B6 SOP 근거·Skill | `hydops/b6_sop/docs/*.md` · `search.py` · `skills/hydraulic-cooling-response/SKILL.md` | |
| Agents | B5 수치 탐지 | `hydops/b5_detect/detector.py` · `evaluate.py` · `product.py` | Agents `labplatform/agents.py` (Skill·MCP·업무 에이전트·Watch) |
| | B7 운영 에이전트 | `hydops/b7_agent/tools.py` · `agent.py` · `skill_loader.py` | |
| Orchestration | B8 승인·조치·재측정 | `hydops/b8_action/executor.py` · `service.py` · `workflow.py` | Process `labplatform/process.py` |
| | B9 관제 화면 | `hydops/b9_dashboard/app.py` · `static/` | Apps `labplatform/apps.py` · `app_templates/ops-console` |
| 공통 | 런타임·도구 서버 | `hydops/runtime.py` · `hydops/mcp_tools.py` | |

실제 uEngine 플랫폼(Data Fabric · Ontology Studio · Process GPT · Ontologic · 아이나루)은 **참고만 했다.** 학생 노트북에서 가볍게 돌도록 같은 개념과 API 모양을 `labplatform/` 에 재현했다. 대응표는 각 콘솔 화면 상단과 교재의 「실제 플랫폼 대응」 절에 있다.

## 2. 설치와 기동

```bash
cd lecture/system
docker compose up -d                       # PostgreSQL :55432 · Neo4j :57474/:57687
uv venv --python 3.12 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt
cp .env.example .env                       # OPENAI_API_KEY 입력 (없으면 HYDOPS_AGENT_MODE=offline)

PYTHONPATH=. .venv/bin/python -c "from hydops.b3_tsdb import store; store.init_schema()"
PYTHONPATH=. .venv/bin/python -c "from hydops.b4_ontology import graph; print(graph.seed_graph())"
PYTHONPATH=. .venv/bin/python -c "from hydops.b6_sop import search; print(search.index_sections())"

scripts/servers.sh local 4                 # 관제 http://localhost:8800  · 플랫폼 http://localhost:8910
scripts/servers.sh platform 4              # 사건 처리를 교육용 플랫폼 프로세스가 맡는다
PYTHONPATH=. .venv/bin/python scripts/bootstrap_platform.py --all   # 강사 준비 (단계별: --upto datasource|ontology|...)
```

컨테이너로 전부 띄우려면 `docker compose --profile app up -d --build` (서버 내부 주소가 달라 bootstrap 의 호스트를 `postgres`·`hydops-api` 로 바꿔야 한다).

| 주소 | 내용 |
|---|---|
| http://localhost:8800 | B9 관제 화면 (시나리오 주입 버튼 포함) |
| http://localhost:8800/mcp/ | MCP 도구 6종 (streamable HTTP) |
| http://localhost:8800/docs | 관제 API 문서 |
| http://localhost:8910/console/ | 교육용 플랫폼 콘솔 |
| http://localhost:8910/apps/hydops-ops/ | 게시된 제조 운영 앱 |
| http://localhost:57474 | Neo4j Browser (`bolt://localhost:57687`, neo4j / hydops-lecture) |

## 3. 데이터

- `data/raw/` — UCI Condition monitoring of hydraulic systems 원본 (2,205 사이클 × 60초). TS1 1 Hz · PS1 100 Hz · FS1 10 Hz · profile(정답 라벨).
- `data/reduced/hydraulic_1s.npz` — 강사 제공 축약본. 모든 센서를 1초 mean/min/max/n 으로 축약.
- 관측 레코드는 `origin_cycle_id`(원본 사이클) · `elapsed_s`(사이클 내 위상) · `ts`(재생 시각, 실제 수집 시각 아님) 를 나눠 둔다.
- UCI 온도는 냉각기 상태에 따라 뚜렷하다: 100% ≈ 36°C, 20% ≈ 45°C, 3% ≈ 56°C (안정 상태 평균).

## 4. 시뮬레이터 모델 (교육용 가정)

```
T_ss = 30 + 15 · load² / cooling_eff        dT/dt = (T_ss − T) / 12s        노이즈 σ = 0.25°C
```

| 상황 | cooling_eff | 부하 1.0 | 부하 0.8 | 결과 |
|---|---|---|---|---|
| 정상 | 1.0 | 45°C | — | 조치 없음 |
| 냉각 성능 저하 | 0.4 | 67.5°C → 경보 | 54°C | 회복 → 종결 |
| 심각한 저하 | 0.25 | 90°C → 경보 | 68.4°C | 미개선 → 이관 |
| HYD-02 팬 증속 | 0.4 × 1.3² | — | 52°C | 회복 → 종결 |

센서 고장(결측·고착·급등)과 명령 실패는 설비 상태와 별도로 주입한다.

## 5. 사건 상태와 분기

`DETECTED → EVIDENCE_READY → PENDING_APPROVAL → EXECUTED → VERIFYING → CLOSED`

| 분기 | 상태 | 조건 |
|---|---|---|
| 센서 오류 | `SENSOR_CHECK` | 5초 이상 결측(GAP)·8초 이상 고착(STUCK) — 설비 조치 보류 |
| 근거 없음 | `HOLD_NO_EVIDENCE` | 적용 SOP·허용 조치 없음, 또는 검색되지 않은 인용 |
| 승인 거부 | `REJECTED` | 사람이 거부 — 실행 기록 없음 |
| 도구 실패·정책 위반 | `ESCALATED` | 명령 실패, 승인값 불일치, 허용 범위 이탈 |
| 미개선 | `ESCALATED` | 재측정 창에서 55°C 이하 10초 연속을 못 채움 |
| 데이터 부족 | `VERIFY_HOLD` | 재측정 창 유효 관측 70% 미만 → 다음 창에서 한 번 더 |
| 실행 종료 | `RUN_ENDED` | 시뮬레이터 초기화로 이전 실행의 열린 사건을 닫음 (회복으로 기록하지 않음) |

## 6. 검증 결과 (2026-09-14 실행)

| 검증 | 명령 | 결과 |
|---|---|---|
| 블록·시나리오 (오프라인 에이전트, 별도 DB `hydops_test`) | `PYTHONPATH=. .venv/bin/python -m pytest tests -q` | 25 passed |
| 시나리오 (실제 LLM gpt-4.1-mini) | `HYDOPS_TEST_AGENT_MODE=llm ... pytest tests/test_scenarios.py` | 18 passed (+ 센서 결측 후 냉각 이상 회귀 테스트 LLM 통과) |
| 플랫폼 폐루프 (LLM + MCP + 프로세스) | `scripts/e2e_platform.py` | 정상 회복 · 승인 거부 · 미개선 · 허용 범위 이탈 · 명령 실패 · 센서 오류 · 처리된 사건의 두 번째 인스턴스(409) 7/7, 중복 시작 거부, 승인 태스크 재완료 409, Golden Question 3/3 |
| 실습 정답·시작본 | `out/labs_verification.txt` | 19개 실습 모두 정답본 통과 · 시작본 실패 |
| UCI 사건 단위 평가 | `python -m hydops.b5_detect.evaluate` | 허용 한계 4σ·3°C: 오탐 1/60 · 누락 0/120 / 2σ·1°C: 오탐 4/60 — 지속 1→10초는 오탐을 바꾸지 않고 지연만 0→9초 (σ≈0.3 이라 실제 한계는 최소 차이 3°C) |
| 임계값 근처 떨림 (시뮬레이터 59.8°C, 10분) | `scripts/make_figures.py` F05 | 경보 신호 지속 1초 99회 · 3초 5회 · 5초 0회 |

실제 실행에서 드러나 고친 문제도 교재의 「흔한 실수」로 옮겼다: 빠른 온도 상승을 급등으로 오판하던 중앙값 규칙, SKILL.md 에 절 번호를 박아 넣어 검색되지 않은 인용이 생긴 일, 실패한 인스턴스가 남긴 열린 사건이 새 감지를 막은 일, OpenAI 함수 스키마가 타입 없는 `list[dict]` 를 거부한 일.

## 7. 폴더

```
system/
├─ hydops/            B1~B9 블록, runtime, golden, mcp_tools
├─ labplatform/       교육용 플랫폼 (fabric · studio · agents · process · apps · console)
├─ skills/            업무 에이전트용 SKILL.md
├─ sql/               PostgreSQL 스키마
├─ scripts/           servers.sh · bootstrap_platform.py · e2e_platform.py · make_figures.py
├─ tests/             pytest (블록·시나리오)
└─ data/              raw(UCI) · reduced(축약본)
```
