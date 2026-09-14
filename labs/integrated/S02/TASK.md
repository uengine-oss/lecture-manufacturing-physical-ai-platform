# 통합반 S02 · 품질 플래그와 시계열 DB (교재 I02 §7)

## 파일
- `quality_lab.py` — 빈칸 `____` 가 있는 실습 파일 (정답본 `solution/quality_lab.py`)
- `test_check.py` — 점검

## 빈칸 위치
| 빈칸 | 변수 | 채울 것 | 힌트 |
|---|---|---|---|
| 1 | `RULES` | `gap_hold_s`, `stuck_run`, `spike_delta["TS1"]` | `system/hydops/config.py` 의 `QualityRules` 와 같은 값 |
| 2 | `LAST_60S_SQL` | 꺼낼 열 두 개, 시간 간격 | 품질 플래그 열 · 원본 사이클 열 · 최근 몇 초? |
| 3 | `NORMAL_RANGE`, `HOLD_RANGE` | 경과 초 (처음, 끝) | 실행 결과 ③ 의 플래그 위치를 보고 고른다 |

## 실행
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python ../labs/integrated/S02/quality_lab.py
```
DB 에는 `LAB-S02-` 로 시작하는 run_id 로만 적재하고, 마지막 ⑤ 단계에서 그 행만 지운다.
테이블 전체 삭제(TRUNCATE)나 `init_schema(reset=True)` 는 쓰지 않는다.

## 확인
```bash
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S02 -q    # 5 passed 이면 완료
```
