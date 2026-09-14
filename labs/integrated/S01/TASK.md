# 통합반 S01 · 센서와 데이터 흐름 알아보기 (교재 I01 §7)

## 파일
- `S01_sensor_flow.ipynb` — 제공 노트북 (빈칸 `____`)
- `solution/S01_sensor_flow.ipynb` — 정답본 (실행 결과 포함)
- `test_check.py` — 점검

## 여는 방법
VS Code 에서 노트북을 열고 커널로 `lecture/system/.venv` 의 Python 을 고른다.
명령줄로 한 번에 실행하려면:
```bash
cd lecture/labs/integrated/S01
../../../system/.venv/bin/jupyter nbconvert --to notebook --execute --inplace S01_sensor_flow.ipynb
```

## 빈칸 위치
| 셀 | 태그 | 채울 칸 |
|---|---|---|
| 3-1 매핑 표 | `mapping` | TS1: sensor_id·unit·hz / PS1: unit·hz·file / FS1: sensor_id·unit·hz·file |
| 3-4 값 하나 설명 | `one_value` | asset_id·raw_value·unit·source_file·is_synthetic |

셀의 태그와 변수 이름(`SENSOR_TABLE`, `ONE_VALUE`)은 바꾸지 않는다. 테스트가 이 셀만 꺼내 검사한다.

## 저장본
4-2 셀이 `saved/` 에 `S01_replay_observations.csv`(540행), `S01_replay_last_frame.png`, `S01_sensor_table.csv` 를 남긴다.
노트북 파일 자체도 저장(Ctrl+S)한다 — 이것이 1회차 체크포인트다.

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S01 -q    # 4 passed 이면 완료
```
마지막 셀(자기 점검)에 `모든 빈칸 통과` 가 나오면 테스트도 통과한다.
