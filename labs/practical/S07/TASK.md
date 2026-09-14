# S07 · 승인 폼·조치 인자 매핑과 조치 도구 정책 검사 (실전반 7회)

교재: `textbooks/실전반/P07_Skill과_조치_흐름_연결.md` §7

## 고칠 파일
| 파일 | 원본 | 틀린 곳 |
|---|---|---|
| `process_cooling_response.json` | `system/labplatform/templates/process_cooling_response.json` | 조치 승인(`approve`) 폼: `event_id` 가 편집 가능, `run_id` 없음, `proposed_value`·`citations` 기본값 변수가 틀림, `citations` 편집 가능 · 조치 실행(`act`) 인자: `approval_id` 없음, `value` 가 승인값이 아닌 제안값, `approved: true` 주장을 넘김 |
| `action_policy.py` | `system/hydops/b8_action/executor.py` `execute_sim_action` | `# TODO(학생)` 1 LLM 의 `approved=True` 를 승인으로 인정 · 2 승인값과 요청값 불일치 검사 없음 · 3 허용 범위 하한 검사 없음 |

`validate_mapping.py` 는 제공 검사기다. 고치지 않는다: `.venv/bin/python ../labs/practical/S07/validate_mapping.py ../labs/practical/S07/process_cooling_response.json`

## 확인
```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S07 -q            # 시작본: 7 failed, 12 passed
LAB_SOLUTION=1 PYTHONPATH=. .venv/bin/python -m pytest ../labs/practical/S07 -q   # 정답본: 19 passed
```

## 규칙
- 테스트는 가짜 저장소(FakeRepo)와 메모리 시뮬레이터만 쓴다. DB·Neo4j 에 쓰지 않는다.
- 플랫폼(:8910)에는 `GET /process/definitions/cooling_response` 만 보낸다. 서버가 없으면 그 테스트는 건너뛴다.
- 고친 템플릿을 플랫폼에 등록하고 인스턴스를 시작하는 일은 교재 활동 3·4 에서 강사 안내에 따라 손으로 한다.

## 개인 설명 과제
세 가지 거부 코드(`APPROVAL_NOT_FOUND`·`VALUE_MISMATCH`·`VALUE_OUT_OF_RANGE`) 중 하나를 골라, 어떤 입력이 어느 줄에서 막히고 사건 상태가 무엇으로 바뀌는지(`service.execute` 참고) 설명한다.
