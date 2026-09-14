# 실전반 S02 · 노이즈를 구별하는 수집 블록 (B2 · B3 확장)

교재: `textbooks/실전반/P02_노이즈를_구별하는_수집_블록.md` §7

## 목표
긴 결측을 정상 값으로 숨기지 않고 판정을 보류하는 품질 검사기를 만든다. 원시 값·정제 값·품질 플래그를 함께 저장하고, 센서 오류와 설비 이상을 다른 상태로 표시한다.

## 고칠 곳 — `quality.py` 의 `# TODO(학생)` 8곳
| 위치 | 지금 동작 (틀림) | 고친 뒤 |
|---|---|---|
| `aggregate_1s` | 결측 샘플(NaN)을 0 으로 채우고 n=hz | 유효 샘플만 집계, n=유효 샘플 수, 유효 < hz×0.5 이면 mean=None |
| `LabQualityChecker.check` 결측 | 항상 MISSING, 정제 값을 직전 유효값으로 채움 | `gap_hold_s`(5) 이상이면 GAP, 정제 값은 None |
| 고착 | `same_run > stuck_run` (9번째부터) | `>= stuck_run` (8번째부터 STUCK) |
| 급등 | 최근 유효값 **중앙값**과 비교, 수준 변화를 받아들이지 않음 | **직전 유효값**과 비교, 3회 연속이면 OK(수준 변화) |
| `store_checked` | 원시 값을 정제 값으로 덮어씀 | 원시 값 보존 |
| `window_state` | 원시 값으로 경보 온도 초과를 세고, 설비 이상을 먼저 판정 | 품질 OK 인 정제 값만 세고, 센서 오류(GAP·STUCK·유효 70% 미만)를 먼저 판정 |

기준값은 `hydops.config.QR`(gap_hold_s=5, stuck_run=8, spike_delta TS1 8°C · PS1 60 bar · FS1 15 L/min)과 `TH`(60°C·10초)를 그대로 쓴다. 급등 기준은 UCI 정상 사이클의 1초 최대 변화(TS1 0.23°C · PS1 40.3 bar · FS1 10.9 L/min)보다 크게 잡은 값이다 — 기준을 바꾸고 싶다면 먼저 정상 동작을 측정한다.

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S02 -q     # 시작본: 7 failed, 1 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S02 -q   # 정답본: 8 passed
```
검사 내용: 사이클 #1500 오류 주입본의 플래그 분포가 OK 49 · SPIKE 1 · MISSING 4 · GAP 3 · STUCK 3 인지, 냉각 심각 저하(0.25) 시뮬레이터의 빠른 상승에서 SPIKE 가 0 인지, 경보 온도 위의 고착이 SENSOR_FAULT 인지, `LAB-S02-` run 으로 저장한 행에서 원시 값이 빈 행이 결측 7초뿐인지.

## 개인 설명 과제
급등 규칙을 중앙값 비교로 두었을 때 냉각 심각 저하 시나리오에서 무엇이 막히는지(사건이 왜 안 생기는지) 설명한다.
