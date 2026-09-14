# S04 · 지속 조건·중복 억제·고정 시험 구간 (실전반 4회)

교재: `textbooks/실전반/P04_이상_이벤트와_첫_관제_화면.md` §7

## 고칠 파일
`detector_lab.py` 의 `# TODO(학생)` 다섯 곳. 원본은 `system/hydops/b5_detect/detector.py`(`ThresholdDetector` 설비 이상 경로), `system/hydops/b3_tsdb/store.py`(`create_event`), `system/hydops/b5_detect/evaluate.py` 다. 시스템 파일은 고치지 않는다.

| 함수 | 틀린 곳 | 고친 뒤 기대 동작 |
|---|---|---|
| `SustainDetector.feed` ① | `raw_value` 로 센다 → 급등(SPIKE) 원시값도 기준 초과로 셈 | 품질 `OK` 인 정제 값 `value` 만 센다 |
| `SustainDetector.feed` ② | 기준 초과가 아니면 무조건 초기화 → 짧은 결측 1~2초가 지속 판단을 끊음 | 초기화는 유효 값이 기준 이하(`OK`)이거나 `GAP` 일 때만. `MISSING`·`SPIKE` 단발은 유지 |
| `EventBook.create` | 신호마다 새 사건 | 같은 설비·유형의 열린 사건이 있으면 `(기존 사건, False)`, `suppressed += 1` |
| `fixed_test_ids` | 부를 때마다 무작위 180 사이클 | `evaluate.fixed_split()` 의 시험 구간(시드 2026) |
| `compare_sustain` | `evaluate(k, δ, smooth, s)` 위치 인자 순서 틀림 | 이름 인자로 `sustain_s` 만 바꾼다 |

`simulate_rows`·`run_stream` 은 제공 함수다(메모리에서만 돈다).

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S04 -q                 # 시작본: 8 failed, 1 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S04 -q  # 정답본: 9 passed
```

정답 기준 하나는 시스템 `ThresholdDetector` 와 같은 시뮬레이터 스트림에서 같은 감지 구간을 내는 것이다.

## 규칙
- DB·Neo4j·서버에 쓰지 않는다. 사건 저장과 화면 표시는 교재 활동 3 에서 제공 서버로 확인한다.
- 시험 구간을 바꾸지 않는다. 매개변수를 고를 때 시험 사이클의 결과를 보고 고르지 않는다.

## 개인 설명 과제
다음 중 하나를 골라 2분 안에 설명한다. (a) `MISSING` 2초가 끼었을 때 시작본과 정답본의 감지 구간이 왜 다른가 · (b) 60°C 경계 스트림에서 지속 1초가 신호 65번을 내도 사건이 1건인 이유 · (c) UCI 시험 구간에서 지속 조건만 바꿔도 오탐 1건(사이클 #1467)이 사라지지 않는 이유.
