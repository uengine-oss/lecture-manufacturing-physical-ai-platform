# 통합반 10회 제출 기록 — 같은 event_id 의 감지·근거·조치·재측정

> 한 사건에 한 장. 모든 칸의 값은 `GET http://localhost:8800/api/events/{event_id}` 또는 교육용 플랫폼 화면에서 **복사**한다. 기억으로 쓰지 않는다.
> 초안 자동 생성: `PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py <event_id> --md`

| 항목 | 값 |
|---|---|
| 팀 / 발표자 / 맡은 역할 | ____ / ____ / 데이터 · 관계·문서 · 에이전트·조치 중 ____ |
| 사례 종류 | 정상 회복 · 승인 거부 · 조치 후 미개선 · 센서 오류 · 중복 요청 중 ____ |
| event_id | ____ |
| asset_id / run_id | ____ / ____ |
| 프로세스 인스턴스 ID (교육용 플랫폼) | PI-____ |
| 앱 URL | http://localhost:8910/apps/hydops-ops/ |

## 1. 감지 (B1→B2→B3→B5)
| event_type | rule_version | 근거 요약(evidence) | 감지 구간 |
|---|---|---|---|
| ____ | ____ | ____ | ____ ~ ____ |

## 2. 근거 (B4·B6→B7)
| decision | action_id / value | 인용(doc_id · version · §) | 도구 호출 순서 | citation_problems |
|---|---|---|---|---|
| ____ | ____ / ____ | ____ | ____ | ____ |

## 3. 조치 (B8, 사람 승인)
| approval_id | 승인자 · 결정 · 승인값 · 승인 시각 | action_log_id | 실행값 · command_status · 실행 시각 | idempotency_key |
|---|---|---|---|---|
| ____ | ____ | ____ (없으면 "실행 없음") | ____ | ____ |

## 4. 재측정 (B8→B1→B2→B3→B5)
| verification_id | outcome | 재측정 창 | 55°C 이하 최장 연속(초) · 유효 비율 | 최종 status |
|---|---|---|---|---|
| ____ | ____ | ____ ~ ____ | ____ · ____ | ____ |

## 5. 합격 목표 검사 (`check_submission.py` 결과를 붙인다)
| 목표 | 결과 | 확인한 기록 |
|---|---|---|
| 근거 없는 조치 0건 | ____ | ____ |
| 승인 없는 실행 0건 | ____ | ____ |
| 중복 실행 0건 | ____ | ____ |
| 재측정 없는 회복 판정 0건 | ____ | ____ |

## 6. 한 줄 설명
- 명령 성공(`command_status`)과 설비 회복(`outcome`)이 다른 필드인 이유: ____
- 프로세스 완료(COMPLETED)가 설비 회복을 뜻하지 않는 이유: ____
