# 통합반 8회 실습 — Process GPT에 업무 Skill 적용

교재: `textbooks/통합반/I08_업무_Skill_적용.md` §7

새 에이전트 프레임워크를 만들지 않는다. **이미 있는 기능을 설정으로 연결**하는 빈칸만 채운다.

## 채울 파일

| 파일 | 빈칸 | 확인 방법 |
|---|---|---|
| `agent_assignment.json` | 할당할 Skill 이름, MCP 서버 이름, 허용 도구 4개 | Skill 은 `SKILL.md` frontmatter 의 `name`, 허용 도구는 frontmatter `tools` 와 같아야 한다. `execute_sim_action`·`verify_recovery` 는 **넣으면 실패**한다 |
| `process_mapping.json` | 프로세스 정의 ID, 인스턴스 키, Watch 행→폼 매핑, 접수 필수 필드, 승인 폼 역할·읽기 전용 기본값·결정 선택지, 승인 기록 값, 실행 도구·인자, 실행으로 가는 결정값 | 제공 템플릿 `process_cooling_response.json`·`watch_events.json` 과 같아야 하고, 플랫폼 엔진의 `render()` 로 채웠을 때 실제 인스턴스의 승인 폼 값과 같아야 한다 |

## 규칙

- 테스트는 GET 만 호출한다: `/agents/skills`, `/agents/mcp-servers`, `/agents/mcp-servers/hydops/tools`, `/process/definitions/cooling_response`, `/process/instances`.
- 승인·거부는 교재 활동 4에서 콘솔 워크리스트로 **손으로** 한다.

## 실행

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S08 -q
```
