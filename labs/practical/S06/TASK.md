# S06 · 플랫폼 어댑터와 로컬·플랫폼 맥락 대조 (실전반 6회)

교재: `textbooks/실전반/P06_플랫폼에서_데이터와_온톨로지_발행.md` §7

## 고칠 파일
`platform_adapter.py` — 에이전트 도구 `get_asset_context` 의 본체를 로컬 Neo4j(`graph.asset_context`) 대신 교육용 플랫폼(Lab Platform) Ontology Studio 의 **발행된** 스키마 `HydraulicOps` 조회로 바꾸는 어댑터.

| 함수 | 틀린 곳 | 고친 뒤 기대 동작 |
|---|---|---|
| `PlatformContext.asset_context` ① | 없는 설비도 `found: True` | `fetch` 결과 0건이면 `{"asset_id", "found": False}` |
| ② | 센서 순서가 플랫폼 응답 순서 | `code` 순 (로컬 `Q_ASSET_SENSORS` 와 같게) |
| ③ | `SOP` 클래스를 `status=active` 로 전체 조회 → HYD-02 에 SOP-COOL-001 이 섞임 | `Asset —GOVERNED_BY→ SOP` 관계로 조회, 사건 유형 `COOLING_ANOMALY`·`SENSOR_FAULT`, 순서 로컬과 같게 |
| ④ | 허용 조치 중복(REDUCE_LOAD 두 번) | `action_id` 로 한 번만 |
| `compare_contexts` | 리스트 전체 `==` 비교 → 발행 클래스에 없는 속성 때문에 늘 불일치, 없는 설비에서 KeyError | 판단에 쓰는 키만 집합 비교, 한쪽에만 있는 키는 `only_local/only_platform`, 로컬에만 값이 있는 속성은 `field_gaps` 로 따로 |

`fetch`·`related`·`invoke`·`recent_state`·`local_context`·`use_context_provider` 는 제공 함수다.

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S06 -q                 # 시작본: 8 failed, 2 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S06 -q  # 정답본: 10 passed
```

1부는 가짜 플랫폼 응답(httpx.MockTransport)으로, 2부는 실행 중인 :8910 의 발행 스키마를 읽기 전용(`objects/fetch`·`related`·`behaviors/invoke`)으로 확인한다. 서버가 없거나 `HydraulicOps` 가 발행되지 않았으면 2부는 건너뛴다(그 경우 플랫폼 실습 완료로 기록하지 않는다).

## 규칙
- `HydraulicOps` 를 다시 가져오거나 발행하지 않는다. 발행을 연습할 때는 `schema_name` 을 `Lab_<팀>` 으로 가져와 쓰고 끝나면 강사에게 알린다.
- 어댑터는 조회만 한다. `binding`·`classes`·`publish` 를 부르지 않는다.

## 개인 설명 과제
(a) 시작본 어댑터로 HYD-03 사건을 처리했을 때 `get_asset_context` 에 SOP 6건이 보였는데도 결정이 HOLD 였던 이유 · (b) `field_gaps` 의 `applicable_sops.approver_role` 이 생기는 원인(발행 클래스 속성)과 그것이 에이전트 판단에 주는 영향 · (c) `GOVERNED_BY` 관계가 `APPLIES_TO` 를 어느 방향으로 읽는지 중 하나를 설명한다.
