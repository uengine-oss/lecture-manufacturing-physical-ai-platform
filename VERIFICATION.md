# 검증 보고 — 강의 패키지 (2026-09-14)

"다 됐다"가 아니라 실행 결과로 남긴다. 명령은 모두 `lecture/system` 에서 실행했다.

## 1. 완성 시스템

| 항목 | 명령 | 결과 |
|---|---|---|
| 블록·시나리오 테스트 (오프라인 에이전트, 별도 DB `hydops_test`) | `PYTHONPATH=. .venv/bin/python -m pytest tests -q` | **25 passed** |
| 시나리오 테스트 (실제 LLM gpt-4.1-mini) | `HYDOPS_TEST_AGENT_MODE=llm … pytest tests/test_scenarios.py` | **18 passed**, 추가 회귀 테스트(센서 결측 뒤 냉각 이상) LLM 통과 |
| 플랫폼 폐루프 리허설 (LLM + MCP + 프로세스) | `scripts/e2e_platform.py` → `out/e2e_platform_report.json` | **7/7** — 정상 회복(CLOSED·RECOVERED) · 승인 거부(REJECTED, 실행 0) · 미개선(ESCALATED, 명령 SUCCEEDED·NOT_IMPROVED) · 허용 범위 이탈 0.4(ESCALATED, 실행 0) · 명령 실패(ESCALATED, FAILED, 재측정 없음) · 센서 오류(SENSOR_CHECK) · 처리된 사건의 두 번째 인스턴스(근거 기록 409, 사건 CLOSED 유지). 중복 시작 `duplicate:true`, 승인 태스크 재완료 409, Golden Question 3/3 |
| 컨테이너 이미지 | `docker build` + 이미지 안에서 `pytest tests/test_blocks.py -k "not golden"` | 빌드 성공 · 5 passed |
| UCI 탐지 평가 (고정 시험 180 사이클) | `evaluate()` 격자 | 허용 한계 4σ·3°C: FP 1 · FN 0 / 2σ·1°C: FP 4 — 지속 1초↔10초는 FP 불변, 지연 0↔9초 |
| 임계값 근처 떨림 (시뮬레이터 59.8°C, 10분) | `make_figures.py` F05 | 경보 신호 지속 1초 99 · 3초 5 · 5초 0 · 10초 0 |
| zero-shot 비교 (Chronos-Bolt tiny) | `python -m hydops.b5_detect.zeroshot` | 시뮬레이터 주입 t=60 → 예측 이탈 t=64 · 규칙 t=82 / UCI 상태별 20 사이클 경보 0·0·0 |

## 2. 실습 (labs)

`out/labs_verification.txt` — 19개 실습 모두 **정답본 통과 · 시작본 실패**.

| 반 | 회차 | 정답본 | 시작본 |
|---|---|---|---|
| 실전반 | S01~S09 | 3·8·6·9·13·10·19·10·20 passed | 모두 1건 이상 실패 |
| 통합반 | S01~S10 | 4·5·5·16·18·24·7·9·6·9 passed | 모두 1건 이상 실패 |

## 3. 교재

- 원본 19편 (`textbooks/실전반/P01~P09`, `textbooks/통합반/I01~I10`) — 템플릿 준수(활동 4개·실습 과제·완료 확인·회고·강사 노트·용어), 이미지 96개 링크 깨짐 0
- 빌드 (`tools/build_textbooks.py --pdf`) — DOCX 19 · 자체 포함 HTML 19 · PDF 19 (11~23쪽), 목차 `textbooks/dist/index.html`

## 4. 설명 영상

`video/video_report.txt` 참고 — 장면 17개, 나레이션 겹침 0, 디코드 오류 0, 화면 검증(DOM 단정) 18항목 통과, 소프트 한국어 자막 포함.

## 4-1. 차수별 실습 영상 (2026-09-15)

`video/lab_videos/README.md` — 19편 모두 합성 검증 통과, 합계 **4.17시간 (250분)**.

| 항목 | 결과 |
|---|---|
| 사양 검증 (`validate_spec.py --run`) | 19/19 OK — 작업 사본에서 실습 실행 기대값 확인 |
| 나레이션 다듬기 | gpt-6-astra (OpenAI Responses API), 장면 398개 |
| 녹화 중 실제 실행 | 실행 장면 70개 모두 기대(실패/통과)와 일치 — 어긋나면 제작 중단 |
| 앱 장면 | 센서 결측→SENSOR_CHECK, 냉각 이상→CLOSED/REJECTED, 심각한 저하→ESCALATED, 플랫폼 흐름→COMPLETED·RECOVERED, 게시 앱 같은 사건 ✔✔✔ |
| 인코딩 | 디코드 오류 0, 평균 음량 −24 dB, 한국어 소프트 자막 |
| 제작 중 발견·수정 | 녹화 영상이 1536×864 영역만 채우고 회색 여백 → 뷰포트 크기로 녹화 후 확대(설명 영상도 원본 크롭으로 재합성) · 데모 실행에 '통과' 배지가 붙는 오해 → '실행 완료' 배지 · 긴 차이 비교가 잘림 → 글자 크기 자동 조절 |

## 5. 제작 중 실제 실행으로 드러나 고친 문제

| # | 발견 경로 | 문제 | 조치 |
|---|---|---|---|
| 1 | 시나리오 테스트 | 급등 판정을 5개 중앙값과 비교해 빠른 온도 상승 전체가 SPIKE 로 막힘 | 직전 유효값 1초 점프 + 3회 연속이면 수준 변화 |
| 2 | LLM 테스트 | SKILL.md 에 절 번호를 박아 검색되지 않은 인용 → HOLD | Skill 에는 "검색 결과에 있는 절만" |
| 3 | LLM 테스트 | HYD-02 는 FAN_BOOST 가 정당한데 오프라인 에이전트는 HOLD | 허용 조치를 그래프에서 읽도록 일반화, 시뮬레이터 팬 증속 구현 |
| 4 | 플랫폼 리허설 | 실패 인스턴스가 남긴 열린 사건이 새 감지를 막음 | 초기화 시 `RUN_ENDED` |
| 5 | 플랫폼 리허설 | OpenAI 함수 스키마가 타입 없는 citations 거부 | `Citation` 타입 명시 |
| 6 | 교재 작성 검증 | FS1 정상 펌프 기동(0→8 L/min)이 SPIKE | 측정한 정상 최대 변화(10.9) 위로 기준 15 |
| 7 | 교재 작성 검증 | HYD-02/03 온도 센서 AFFECTS 근거가 HYD-01 전용 SOP | 설비별 근거, SOP 없는 설비는 시뮬레이터 가정 |
| 8 | 교재 작성 검증 | 앱 승인값 0.8 고정 → HYD-02 승인 시 범위 이탈 | 워크아이템 폼 값으로 초기화 |
| 9 | 교재 작성 검증 | 다른 인스턴스가 처리된 사건을 EVIDENCE_READY 로 되돌릴 수 있음 | DETECTED 가 아니면 409 |
| 10 | 교재 작성 검증 | 적재 API 가 탐지를 거치지 않음 · 별칭 중복 허용 | 같은 탐지 경로, 별칭 충돌 409 |
| 11 | 교재 작성 검증 | **F05·README·나레이션이 오탐 감소를 지속 조건 덕으로 설명 (틀림)** | 격자 재평가로 허용 한계 효과임을 확인, 그림·문서·영상 수정, 지속 조건 효과는 떨림 실험으로 따로 제시 |
| 12 | 교재 작성 검증 | 시스템 테스트가 공유 DB 사건을 TRUNCATE | 별도 DB `hydops_test` |
| 13 | 교재 작성 검증 | 오프라인 검색 인덱스 없음 · Golden Q2 SOP 하드코딩 · 발행 후 매핑 변경이 조회에 반영 · MCP 최근 구간이 사건 시점에 고정되지 않음 | 인덱스 자동 생성 · 관계 체인 · 발행 스냅샷 · `event_id` 고정 |
| 14 | 영상 리허설 | 이미 끝난 센서 결측이 60초 창에 남아 실제 냉각 이상을 센서 오류로 보류 | 현재 센서 상태는 최근 15초로 판단 + 회귀 테스트 |
