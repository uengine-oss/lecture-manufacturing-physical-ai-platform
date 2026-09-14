# 실전반 S01 · 첫 데이터가 흐르는 시스템 (B1 → B2 → B3)

교재: `textbooks/실전반/P01_첫_데이터가_흐르는_시스템.md` §7

## 목표
UCI 원본 CSV 세 개(TS1 1 Hz · PS1 100 Hz · FS1 10 Hz)를 공통 관측 레코드로 매핑하고, 제공 품질 검사기(B2)와 제공 적재 함수(B3)로 PostgreSQL 에 넣은 뒤, 최근 60초를 조회해 **원본 사이클을 추적**한다.

## 고칠 곳 — `mapping.py` 의 `# TODO(학생)` 9곳
| 함수 | 지금 동작 (틀림) | 고친 뒤 |
|---|---|---|
| `reduce_to_seconds` | 1초 구간의 첫 샘플만 고른다, n=1 | 1초 mean·min·max·n(원본 샘플 수) |
| `map_cycle` | origin_cycle_id 없음, 단위 전부 °C, agg 없음, is_synthetic=True | 센서별 단위, 원본 사이클, 고주파 센서 agg{min,max,n,source_hz}, 원본은 합성 아님 |
| `load_cycles` | run.source='simulator', 모든 사이클이 같은 재생 시각 | source='uci_replay', i 번째 사이클은 60×i 초 뒤 |
| `window_with_origin` | run_id 로 거르지 않음 → 수업 서버 시뮬레이터 관측을 읽는다 | run_id 로 거른다 |

제공 함수(`read_raw_cycle`, `delete_lab_run`)와 `SENSOR_SPEC`, `LAB_REPLAY_START` 는 고치지 않는다.

## 규칙
- run_id 는 반드시 `LAB-` 로 시작한다. 실습이 끝나면 `delete_lab_run(run_id)` 로 자기 행만 지운다.
- 재생 시각은 `LAB_REPLAY_START`(2026-09-01 00:00 UTC)에서 시작한다. 재생 시각은 실제 수집 시각이 아니다.
- `store.init_schema(reset=True)`, 테이블 TRUNCATE 는 금지한다.

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S01 -q     # 시작본: 3 failed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S01 -q   # 정답본: 3 passed
```
테스트는 사이클 100·101·102 를 `LAB-S01-xxxxxxxx` run 으로 적재하고, 마지막 60초가 사이클 102 의 elapsed 0~59 인지, 재생 시작 +90초 기준 60초가 사이클 100·101 에 걸치는지 확인한 뒤 행을 지운다.

## 개인 설명 과제
`window_with_origin` 에서 run_id 조건을 뺐을 때 어떤 run 의 관측이 나오는지, 그것이 왜 "원본/합성 구분"을 깨는지 한 문단으로 설명한다.
