# S09 · 게시 앱 설정·바인딩과 새 센서 별칭 매핑 (실전반 9회)

교재: `textbooks/실전반/P09_관제_앱_게시와_통합_시연.md` §7

## 고칠 파일
| 파일 | 기준 | 틀린 곳 |
|---|---|---|
| `config.js` | `system/labplatform/apps.py` 필수 바인딩, 게시본 `labplatform/data/apps/hydops-ops/config.js` | `platform_api` 포트, `schema_name`, `process_def_id` 키 이름 |
| `binding.js` | `system/labplatform/app_templates/ops-console/index.html` 의 fetch 호출 | 사건 목록 관계(`HAS_EVENT`), 사건 상세를 읽는 서버(`hydops_api`), 업무 시작 입력(`event.event_id`, `run_id` 누락), 승인 초안의 승인값(이전 제공 화면의 0.8 고정 결함 → 워크리스트 폼 `approved_value` 에서 가져오기. 현재 `index.html` 은 `draftFor` 로 태스크마다 폼 값을 넣도록 고쳐져 있다) |
| `alias_mapping.py` | `system/hydops/b9_dashboard/app.py` `PUT /api/sensors/{sensor_id}/aliases`(목록 전체 교체, 같은 설비 이름 충돌 409) · `POST /api/ingest/{asset_id}`(매핑 → 품질 검사 → 저장 → 탐지, 응답 `inserted`·`flags`·`events`) | `# TODO(학생)` 1 대소문자 무시·부분 문자열 매칭 · 2 모르는 별칭을 조용히 버림 · 3 게이트웨이 단위를 그대로 씀 |

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S09 -q            # 시작본: 16 failed, 4 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S09 -q   # 정답본: 20 passed
```

## 규칙
- 테스트는 앱을 게시하지 않고, 별칭을 PUT 하지 않고, 관측을 적재하지 않는다. 서버에는 GET 만 보낸다(`related/HAS_EVENT`, `/api/events/{id}`).
- 게시·별칭 등록·게이트웨이 적재는 교재 활동 3·4 에서 강사가 정한 순서로 손으로 한다.

## 개인 설명 과제
`TT-101` 이 `TS1` 으로 매핑되는 경로(그래프 별칭 → 표준 코드·단위 → 품질 검사 → 적재)와, `oil_temp_B` 가 섞인 묶음이 왜 한 행도 적재되지 않아야 하는지 설명한다.
