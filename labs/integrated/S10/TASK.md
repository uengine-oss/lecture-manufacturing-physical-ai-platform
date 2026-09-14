# 통합반 10회 실습 — 전체 아키텍처 폐루프 시연

교재: `textbooks/통합반/I10_전체_아키텍처_폐루프_시연.md` §7

## 채울 파일

| 파일 | 빈칸 | 확인 방법 |
|---|---|---|
| `check_submission.py` | 규칙 조건 11곳: 성공 조치 최대 개수, 승인·회복·종결 값, 종결 행위자, 인용 0개 조건, 승인 ID·실행 시각·중복 방지 키·재측정 창 시작 필드, 회복 재측정 최소 개수 | ① 실제 기록(fixtures, 2026-09-14 GET 결과)은 네 목표를 모두 통과 ② 한 곳만 바꾼 위반 사례 14가지는 모두 걸림 ③ `GET /api/events?all_runs=true` 의 모든 사건이 통과 |
| `SUBMISSION_TEMPLATE.md` | 발표용 제출 기록 (테스트하지 않음) | 한 사건의 감지·근거·조치·재측정을 같은 event_id 로 채운다 |

## 네 가지 합격 목표를 기록으로 바꾸면

| 목표 | 기록 조건 |
|---|---|
| 근거 없는 조치 0건 | 실행 기록이 있으면 제안 인용이 1개 이상, 인용 검증 문제 0개, 인용한 절 본문이 그래프에 있음 |
| 승인 없는 실행 0건 | 모든 실행 기록의 `approval_id` 가 같은 사건의 APPROVED 승인이고, 승인 시각 ≤ 실행 시각, 승인값 = 실행값 |
| 중복 실행 0건 | `idempotency_key` 가 겹치지 않고, 성공한 조치가 1건 이하 |
| 재측정 없는 회복 판정 0건 | CLOSED 이면 조치 이후 창의 RECOVERED 재측정이 1건 이상이고, CLOSED 전이 행위자가 verifier |

## 실행

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S10 -q
PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py --all
PYTHONPATH=. .venv/bin/python ../labs/integrated/S10/check_submission.py <event_id> --md > 제출_<event_id>.md
```

검사기는 GET 만 한다. 사례를 새로 만드는 주입·승인은 교재 활동 1~3에서 화면으로 한다.
