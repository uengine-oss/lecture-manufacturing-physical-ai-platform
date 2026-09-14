# S08 · 재측정 판정 고치기 (실전반 8회)

교재: `textbooks/실전반/P08_플랫폼에서_조치와_재측정_폐루프.md` §7

## 고칠 파일
`recovery.py` — 원본 `system/hydops/b8_action/executor.py` 의 `verify_window`·`verify_recovery` 를 메모리 관측 행에 적용하도록 옮긴 복사본.

| TODO | 증상 | 드러내는 테스트 |
|---|---|---|
| 1 | 창의 시작을 자르지 않아 조치 전 관측(정상 45°C)이 회복 근거로 섞인다 | `test_pre_action_observations_are_ignored`, `test_severe_degradation_not_improved_although_command_succeeded` |
| 2 | 결측 행을 먼저 지워 유효 비율이 늘 100% 가 된다 | `test_missing_rows_count_against_valid_ratio`, `test_dropout_in_window_is_insufficient_data` |
| 3 | 명령 성공 + 마지막 값이 60°C 아래면 회복으로 본다 | `test_command_success_alone_is_not_recovery`, `test_below_alarm_but_above_recovery_is_not_improved` |

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S08 -q            # 시작본: 6 failed, 4 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S08 -q   # 정답본: 10 passed
```

시뮬레이터 테스트는 `materials/figures/figures_data.json` 의 F07 값(회복 연속 56초 · 미개선 0초 · 데이터 부족 유효 25%, 연속 11초)과 같은 값을 기대한다.

## 규칙
DB 에 쓰지 않는다. 관측은 `HydraulicSimulator(seed=7)` → `SensorQualityChecker` → `ThresholdDetector` 로 메모리에서 만든다. 실제 서버의 냉각 이상 주입은 교재 활동 1 에서 강사 안내로 한 번만 한다.

## 개인 설명 과제
세 갈래(RECOVERED·NOT_IMPROVED·INSUFFICIENT_DATA) 중 하나를 골라 `metrics` 의 어떤 값이 판정을 결정했는지, 그리고 그 판정이 `service.verify` 에서 어떤 사건 상태가 되는지 설명한다.
