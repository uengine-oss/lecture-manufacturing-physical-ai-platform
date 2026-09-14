# 실전반 S03 · Neo4j로 설비 관계 연결 (B4 구현 · B3 확장)

교재: `textbooks/실전반/P03_Neo4j로_설비_관계_연결.md` §7

## 목표
세 가지 파라미터 Cypher 질의를 고쳐 **HYD-02 에 HYD-01 의 SOP 가 절대 섞이지 않게** 하고, 그래프 결과를 asset_id 로 PostgreSQL 최근 구간과 결합한다.

## 고칠 곳 — `context_queries.py` 의 `# TODO(학생)` 6곳
| 위치 | 지금 동작 (틀림) | 고친 뒤 |
|---|---|---|
| `Q_ASSET_SENSORS` | 센서 코드만으로 찾아 세 설비의 센서 9개 | `$asset_id` 설비에서 `HAS_SENSOR` 로 출발 → 3개 |
| `Q_APPLICABLE_SOP` | 도착 설비를 묶지 않음, status 필터 없음 → HYD-02 에 SOP-COOL-001 v1·v2, SOP-LOAD-001 이 섞임 | `APPLIES_TO` 도착 설비 = `$asset_id`, `status='active'` |
| `Q_ASSET_CONTEXT` | SOP 를 필수 MATCH → HYD-03 이 `found: False`, 폐기 SOP 포함 | `OPTIONAL MATCH` + active 만 → HYD-03 은 `found: True, active_sops: []` |
| `join_recent` | run_id 미전달, 그래프 `sensor_id`('HYD-02.TS1')로 관측 요약('TS1')을 찾음 | run_id 로 거르고 `Sensor.code` 로 결합 |

그래프는 **읽기만** 한다. `graph.reset_graph()`·`seed_graph()` 는 실습에서 호출하지 않는다(강사가 적재해 둔다).

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S03 -q     # 시작본: 5 failed, 1 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S03 -q   # 정답본: 6 passed
```
결합 테스트는 UCI 사이클 100 을 HYD-02 의 `LAB-S03-` run 으로 적재(재생 시각 2026-09-03)하고, 세 센서가 60개씩 결합되고 단위가 그래프와 일치하는지 본 뒤 행을 지운다.

## 개인 설명 과제
`Q_APPLICABLE_SOP` 에서 `(a:Asset {asset_id:$asset_id})` 를 뺐을 때 HYD-02 에 어떤 SOP 가 섞이는지, 그 결과가 B7 에이전트의 조치 제안에서 어떤 위험이 되는지 설명한다.
