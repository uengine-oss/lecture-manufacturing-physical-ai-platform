# 통합반 S03 · Neo4j 로 설비와 매뉴얼 연결 (교재 I03 §7)

## 파일
- `graph_lab.py` — 빈칸 `____` 가 있는 실습 파일 (정답본 `solution/graph_lab.py`)
- `test_check.py` — 점검

## 빈칸 위치
| 빈칸 | 변수 | 채울 것 |
|---|---|---|
| 1 | `MERGE_SENSOR`, `SOP_KEY_COOL_V2` | 센서 ID 를 만드는 구분 문자, SOP 키(`문서ID@v판번호`) |
| 2 | `Q_ASSET_SENSORS` | 설비 → 센서 관계 이름 |
| 3 | `Q_APPLICABLE_SOP` | SOP → 설비 관계 이름, 유효한 판의 status 값, SOP → 조치 관계 이름 |
| 4 | `Q_EVENT_EVIDENCE` | 사건 → 설비, 사건 → 절, SOP → 절 관계 이름 |
| 5 | `sensors_with_recent_values` | 그래프 결과에서 PostgreSQL 조회에 넘길 열쇠 |

관계 이름은 `system/hydops/b4_ontology/graph.py` 의 `seed_graph` 에서 찾는다.

## 실행
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python ../labs/integrated/S03/graph_lab.py
```
- 질의는 읽기 전용 세션으로 실행한다.
- MERGE 는 강사 시드와 같은 값일 때만 반영되고, ID 가 틀려 새 노드가 생기면 되돌린다(`committed: False`).
- 활동 4 는 `LAB-S03-` run 으로 사이클 #100 을 적재했다가 끝나면 지운다.

## 확인
```bash
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S03 -q    # 5 passed 이면 완료
```
질문 3 테스트는 인용이 연결된 사건이 그래프에 없으면 건너뛴다(skip). 강사가 관제 화면에서 사건을 하나 처리해 두면 실행된다.
