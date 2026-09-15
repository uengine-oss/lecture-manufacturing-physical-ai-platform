# 차수별 실습 영상 — 장면 사양(spec) 작성 지침

한 교재 = 한 영상 = `specs/<ID>.json` 하나 (`ID` 는 P01~P09, I01~I10).
사양의 나레이션 초안은 작성자가 쓰고, `tools/polish.py` 가 **gpt-6-astra** 로 자연스러운 한국어 말투로 다듬는다.

## 영상 구성 (순서 고정)

| 구간 | 장면 유형 | 목적 |
|---|---|---|
| 1. 여는 장면 | `title` 1개 | 몇 회차인지, 오늘 무엇을 만드는지, 전체 시스템에서의 위치 |
| 2. 기본 개념 | `concept`·`image`·`code` 4~7개 | 처음 듣는 학생도 따라오게 **쉬운 말과 비유**로. 용어는 처음 나올 때 풀어서 |
| 3. 실습 과정 | `task`·`code`·`run`·`apply_fix`·`app` 4~8개 | 교재 활동과 실습 과제를 실제로 한다. 시작본 실행(실패) → 무엇이 틀렸는지 → 고치기 → 다시 실행(통과) |
| 4. 퀴즈 | `quiz` 1개 (문항 3개) | 오늘 핵심을 스스로 확인. 객관식 또는 짧은 답 |
| 5. 해답 | `answer` 1개 | 정답과 **왜 그런지** |
| 6. 요약 | `summary` 1개 | 3~5줄 |
| 7. 다음 차수 | `next` 1개 | 다음 회차 제목·날짜·무엇을 하는지 (마지막 회차는 과정 마무리와 발표 안내) |

전체 12~20 장면, 나레이션 합계 **7~12분**. 장면당 나레이션 15~50초(한국어 약 7자/초).

## 공통 필드

```json
{
  "id": "P01",
  "class": "실전반",
  "session": 1,
  "title": "첫 데이터가 흐르는 시스템",
  "date": "2026-10-31 (토)",
  "blocks": "B1 · B2 · B3",
  "textbook": "textbooks/실전반/P01_첫_데이터가_흐르는_시스템.md",
  "lab": "labs/practical/S01",
  "next": {"id": "P02", "title": "노이즈를 구별하는 수집 블록", "date": "2026-11-07 (토)"},
  "scenes": [ { "type": "...", "caption": "화면 아래 짧은 자막 바 (20자 안팎)", "narration": "초안", ... } ]
}
```

모든 경로는 `lecture/` 기준 상대 경로. 이미지는 `materials/...` 에 이미 있는 것만 쓴다(없으면 만들지 말고 `concept` 로 설명).

## 장면 유형

| type | 추가 필드 | 화면 |
|---|---|---|
| `title` | `subtitle`, `points`(오늘 할 일 3개) | 회차 카드 + 로드맵 |
| `concept` | `heading`, `points`[2~5], `image`?(materials 경로), `analogy`?(한 줄 비유), `note`?(주의 한 줄) | 설명 슬라이드. image 가 있으면 좌우 배치 |
| `image` | `heading`, `image`, `caption`? | 그림·실제 화면 크게 |
| `code` | `heading`, `file`(lecture 기준), `lines`: [시작, 끝], `highlight`: [줄번호…], `note`? | 코드 편집기 화면. 파일은 실제로 읽어 보여 준다 |
| `task` | `heading`, `steps`[…], `files`[…] | 실습 과제 안내 (무엇을 고치나) |
| `run` | `heading`, `cmd`, `expect`: `"fail"`\|`"pass"`, `tail`?(보여 줄 마지막 줄 수, 기본 14), `demo`?: true (테스트가 아니라 출력만 보여 주는 실행 — 배지를 '실행 완료'로 표시) | **실제로 실행해 녹화한다.** `cmd` 는 `lecture/system` 에서 실행. 실습 폴더는 `{WORK}` 로 쓴다 (예: `PYTHONPATH=. .venv/bin/python -m pytest {WORK} -q -p no:warnings`). 기대와 결과가 다르면 제작이 멈춘다 |
| `apply_fix` | `heading`, `file`(실습 폴더 안 상대 경로, 예 `mapping.py`), `focus`?[검색어…] | 시작본과 정답본의 차이를 보여 주고 **작업 사본에 실제로 적용**한다 |
| `app` | `heading`, `action`, `params` | 실제 화면 조작을 녹화 (아래 목록) |
| `quiz` | `questions`: [{`q`, `choices`?[…]}] ×3 | 문제 화면. 나레이션은 문제를 읽고 "잠시 멈추고 풀어 보세요" |
| `answer` | `answers`: [{`a`, `why`}] ×3 | 정답과 이유 |
| `summary` | `points`[3~5] | 요약 |
| `next` | `points`[2~3] | 다음 차수 예고 |

### `app` 동작 목록

| action | params | 내용 | 서버 모드 |
|---|---|---|---|
| `dashboard` | `asset`?, `inject`?: dropout\|stuck\|spike\|cooling\|severe, `decision`?: approve\|reject\|none, `focus`?: chart\|events\|detail | 관제 화면. 주입하면 사건이 생기고, decision 에 따라 승인/거부 후 결과까지 따라간다 | local |
| `neo4j` | `cypher` | Neo4j Browser 에서 질의 실행 | 무관 |
| `console` | `tab`: home\|fabric\|studio\|agents\|process\|apps, `do`?: fetch\|golden\|call_tool\|watch_tick\|sql | 교육용 플랫폼 콘솔 화면 | platform |
| `platform_flow` | `inject`?: cooling, `decision`: approve\|reject, `value`? | Watch → 에이전트 → 승인 태스크 → 인스턴스 완료 | platform |
| `app_page` | — | 게시된 제조 운영 앱에서 사건 열기 | platform |
| `notebook` | `path`(lecture 기준 .ipynb) | 노트북을 HTML 로 변환해 스크롤 | 무관 |
| `api` | `method`, `url`, `body`? | API 호출과 응답을 터미널 화면에 보여 준다 (읽기 위주) | 무관 |

## 나레이션 초안 원칙

- **쉽게.** 2학년이 처음 들어도 이해할 문장. 용어는 "품질 플래그, 그러니까 이 값이 믿을 만한지 붙여 두는 표시" 처럼 풀어 준다.
- 장면에 **보이는 것**을 가리키며 말한다 ("화면 왼쪽의 빨간 점이…").
- 숫자·코드·파일 이름은 교재와 실제 실행 결과 그대로. 지어내지 않는다.
- 실라버스 금지 혼동을 지킨다: 설비 상태 라벨 ≠ 제품 불량, 재생 시각 ≠ 수집 시각, 규칙 감지 ≠ zero-shot, 명령 성공 ≠ 회복, 업무 완료 ≠ 설비 회복, 교육용 플랫폼 ≠ 실제 플랫폼.
- 실전반은 "고치고 검증", 통합반은 "빈칸을 채우고 확인" 이라는 차이를 살린다.
- 퀴즈는 외우기가 아니라 **판단**을 묻는다 (예: "센서가 7초 끊겼다. 설비 조치를 해야 할까?").

## 검증

`python tools/validate_spec.py <ID>` — 구조, 파일·이미지 존재, `code` 줄 범위, `apply_fix` 대상 존재, 문항 수를 확인한다.
`python tools/validate_spec.py <ID> --run` — 작업 사본을 만들어 `run` 장면을 순서대로 실제 실행하고 기대(fail/pass)를 확인한다.

### `apply_fix` 의 `function`
`"function": "reduce_to_seconds"` 를 주면 그 **최상위 함수 하나만** 정답본으로 바꾼다. 여러 장면에 나눠 한 함수씩 고치고, 사이에 `run` 을 넣어 실패 수가 줄어드는 과정을 보여 줄 수 있다. 빠뜨린 함수가 있으면 마지막 `run` 이 `pass` 가 되지 않아 제작이 멈춘다. 파이썬이 아닌 파일(JSON·SKILL.md·ipynb 등)은 `function` 없이 파일 전체를 바꾼다.

### 확장판(기초 보강) 필드
- 사양 최상위 `"target_minutes": 24` — 길이 검증 기준을 바꾼다.
- `concept` 에 `snippet`(예제 코드 문자열), `snippet_title`, `output`(실행 결과 문자열 — 반드시 실제로 실행한 출력)을 주면 오른쪽에 편집기·결과 창을 그린다.
- `code` 에 `explain`: [{"k": "문법/줄", "v": "쉬운 설명"}] 을 주면 코드 옆에 설명 카드를 붙인다.
- `review`: `heading`, `points`[…], `note`? — 구간 끝 복습 카드. 섹션은 앞 장면을 따른다.
- 파이썬 문법 시연은 `demos/<ID>/*.py` 파일을 `code` 로 보여 준 뒤 `run`(`demo: true`)으로 실제 실행한다.
- 사양 최상위 `"polish_ratio": 0.8` — gpt-6-astra 다듬기에서 초안 길이를 이 비율로 줄인다(핵심 설명·숫자 유지). 길이 검증도 이 비율로 계산한다.
