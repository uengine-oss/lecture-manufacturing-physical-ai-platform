# 통합반 S06 · 도구를 쓰는 로컬 에이전트와 상태표 (교재 I06 §7)

빈칸 `____` 을 채운다. 공유 DB·Neo4j·서버에 쓰지 않는다. 실제 `run_offline_agent`·`verify_citations`·`executor`·`service` 코드를
`lab_fakes.py` 의 메모리 저장소(run_id `LAB-S06`)에 연결해 돌린다.

| 파일 | 채울 곳 |
|---|---|
| `lab_agent.py` | 사건 → `get_recent_window` → `get_asset_context` → `search_sop` → `propose_action` 도구 이름, 센서 오류 분기, HOLD, 조치 값 필드 |
| `approval_wiring.py` | 승인 API 경로, 버튼 → APPROVED/REJECTED, 조치 → 시뮬레이터 메서드(`apply_load`, `apply_fan_boost`), 거부 시 값 |
| `state_table.py` | 10개 상황 × (다음 status, action_log 수, 거부 코드) |
| `lab_fakes.py` | 제공 — 수정하지 않는다 |

점검 내용
- 다섯 사건(HYD-01 냉각·결측, HYD-02 냉각, HYD-03 냉각, 이미 실행된 사건)에서 결정·조치·값·인용·도구 순서가 제공 오프라인 에이전트와 같고, 부하는 1.0 그대로(승인 전 미실행)
- 승인/거부 버튼 본문이 `app.js` 와 같고, 실제 `service` 로 승인 → 부하 0.8·VERIFYING, 거부 → REJECTED
- 상태표가 실제 `service` 실행 결과와 같다: 거부·명령 실패·허용 범위 이탈·승인 기록 없음·중복 승인·회복·미개선·데이터 부족(첫 창 → 다음 창)

```bash
cd lecture/system
HYDOPS_AGENT_MODE=offline PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S06 -q          # 모두 채우면 24 passed
LAB_SOLUTION=1 HYDOPS_AGENT_MODE=offline PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S06 -q   # 정답본
```
