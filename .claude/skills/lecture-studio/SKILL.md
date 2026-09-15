---
name: lecture-studio
description: >
  실라버스·강의계획서(docx/pdf/md)를 받아 실제로 동작하는 강의용 완성 시스템을 만들고, 실제 실행 결과만으로
  설명 영상, 시각 자료(데이터 그림·개념도·실제 화면), 차수별 교재(DOCX·HTML·PDF), 실습 과제(시작본·정답본·자동 검증),
  차수별 실습 영상(개념→실습 실행→퀴즈→해답→요약→다음 차수, gpt-6-astra 나레이션 다듬기·OpenAI TTS·한국어 자막)까지
  한 번에 제작하는 절차. "실라버스로 강의 만들어", "강의계획서 보고 교재·실습·영상", "차수별 교재", "실습 영상 녹화",
  "강의 패키지", "교육과정 콘텐츠 제작", "/lecture-studio" 같은 요청에 사용한다. 기존 강의의 영상 한 편을 기초 보강판으로
  늘리거나(“2배로 쉽게”), 실습 영상만 다시 만드는 경우에도 사용한다.
---

# Lecture Studio — 실라버스에서 강의 패키지까지

**한 줄 원칙: 보여 주는 모든 숫자·화면·출력은 실제로 실행한 결과여야 한다.** 교재의 예상 출력, 영상 속 테스트 결과, 그림의 수치 모두 그렇다. 기대와 다르면 만들기를 멈추고 시스템이나 설명을 고친다 — 이 과정에서 드러난 결함이 곧 좋은 교재 소재다.

실제 사례(제조 피지컬 AI 강의, 19회차): 완성 시스템 + 설명 영상 7분 + 그림 34장 + 교재 19편 + 실습 19개 + 실습 영상 19편(4시간 10분). 사례 산출물 경로와 수치는 `references/case-hydops.md`.

## 산출물 구조 (강의 저장소)

```
<lecture>/
├─ system/            완성 시스템 (+ tests/, scripts/, 교육용 대체 플랫폼이 필요하면 여기)
├─ materials/         figures/(데이터 그림) · diagrams/(개념도) · screenshots/(실제 화면) · index.html
├─ textbooks/<반>/    차수별 교재 Markdown · dist/(docx·html·pdf) · _AUTHORING_GUIDE.md
├─ labs/<반>/SXX/     TASK.md · 시작본 · solution/ · test_check.py
├─ video/             설명 영상 · lab_videos/(specs/, <반>/*.mp4·srt, README.md)
├─ README.md · VERIFICATION.md
```

## 단계 (체크포인트마다 숫자로 보고한다)

| 단계 | 할 일 | 끝났다는 증거 |
|---|---|---|
| 0. 실라버스 분석 | `pandoc x.docx -t markdown`, 그림 추출(`unzip`), 회차표·블록·완료 확인 문구를 표로 옮긴다. 사용할 기존 플랫폼이 "참고만"인지 "실제 연동"인지 사용자에게 확인한다 | 회차 × 블록 표 |
| 1. 완성 시스템 | 실라버스 아키텍처 블록 그대로 구현. 공개 데이터가 있으면 내려받아 실제 데이터로. 외부 플랫폼이 무겁거나 참고만이면 **같은 개념·API 모양의 교육용 경량 구현**을 만든다 | 단위·시나리오·E2E 테스트 통과 수, LLM 모드 테스트 |
| 2. 실패 분기 리허설 | 정상 경로 + 실라버스가 요구하는 실패 분기(거부·미개선·데이터 부족·중복·도구 실패)를 스크립트로 끝까지 돌린다 | `e2e_*.py` 사례 n/n |
| 3. 시각 자료 | 데이터 그림(matplotlib, 실제 결과), 개념도(HTML/SVG → Playwright 캡처), 실제 화면(Playwright 연출·DOM 단정) | 그림 목록 + 각 수치 출처 JSON |
| 4. 설명 영상 | 서사 대본 → 금지 표현 검사 → TTS → 녹화(슬라이드+실제 실행) → 합성·자막 | 겹침 0, 디코드 오류 0, 화면 단정 통과 수 |
| 5. 교재·실습 | 작성 지침(사실표·템플릿·그림 목록·실습 규칙)을 먼저 쓰고 병렬 작성자에게 나눈다 | 교재 n편 이미지 링크 깨짐 0, 실습 정답 통과·시작본 실패 n/n |
| 6. 실습 영상 | 회차별 장면 사양 → `validate_spec --run` → gpt-6-astra 다듬기 → TTS → 렌더 → 합성 | 실행 장면 기대 일치 n/n, 디코드 0 |
| 7. 빌드·배포 | 교재 docx/html/pdf, 갤러리, README/VERIFICATION, 비밀 스캔 후 커밋·푸시 | 비밀 0, 푸시 해시 |

각 단계 세부 절차: `references/pipeline.md`. 실제로 걸린 함정: `references/lessons-learned.md` — **시작 전에 반드시 읽는다.**

## 병렬화

- 교재·실습 작성과 실습 영상 사양 작성은 회차 묶음(3회차씩)으로 서브에이전트에 나눈다. 프롬프트 틀: `references/subagent-prompts.md`.
- 공유 서버·DB 를 쓰는 작업은 규칙을 박아 둔다: 리셋·재시작·상태 변경 호출 금지, 쓰기는 `LAB-` 접두 행만, 끝나면 자기 행 삭제.
- 작성자가 시스템 결함을 보고하면 **문서로 우회하지 말고 시스템을 고친 뒤** 해당 작성자에게 재동기화를 요청한다.
- 서버 모드 전환(재시작)이 필요한 렌더는 모드별 대기열로 직렬화한다(`after.sh`).

## 실습 영상 도구 (`scripts/lab_videos/`)

```bash
export LECTURE_ROOT=<강의 루트> OPENAI_ENV_FILE=<OPENAI_API_KEY 가 있는 .env> PYTHON=<파이썬>
python scripts/lab_videos/validate_spec.py P01 --run     # 작업 사본에서 실습 실행 기대(fail/pass) 확인
scripts/lab_videos/produce.sh P01 P02                   # 검증 → gpt-6-astra → TTS → 렌더 → 합성
scripts/lab_videos/after.sh "P02" P03                   # 앞 제작이 끝나면 이어서
python scripts/lab_videos/sheet.py P01                   # 장면별 프레임 모음으로 눈 검사
python scripts/lab_videos/index.py                       # README.md · index.html
```

사양 스키마: `references/lab-video-spec-guide.md` · 예시: `examples/hydops/lab_video_spec_P01_12min.json`(표준 12분), `lab_video_spec_P01_extended.json`(기초 보강 26분). `app_actions.mjs` 는 **도메인마다 고쳐 쓰는** 화면 조작 모음이다.

필요 조건: Node 22+ (처음 한 번 `cd scripts && npm install` — ESM 은 스크립트 위치 기준으로 모듈을 찾는다), ffmpeg, Python(openai, python-dotenv), OpenAI 키(gpt-6-astra · gpt-4o-mini-tts). 다른 다듬기 모델을 쓰려면 `polish.py` 의 `MODEL`.

## 기초 보강판 (영상을 2배로 쉽게)

기존 사양을 `specs_archive/` 에 보관하고 다음을 넣는다 (`references/pipeline.md` §6-3):
- 구간을 부로 나누고(시스템·데이터 기초 / 언어 문법 / 핵심 개념 / 저장·테스트 / 실습) 각 부 끝에 `review` 장면
- 코드 장면에 `explain`(문법 한 줄 풀이 카드), 개념 장면에 `snippet`+`output`(실제 실행 결과)
- 문법 시연 스크립트를 `demos/<ID>/` 에 두고 `code` → `run(demo:true)` 로 실제 실행
- 고친 뒤의 정답 코드도 `code`+`explain` 으로 다시 읽어 반복 학습
- `target_minutes`, `polish_ratio`(0.8 — gpt-6-astra 가 초안을 늘리는 경향을 상쇄)로 길이를 맞춘다

## 사용자에게 먼저 확인할 것

- 기존 플랫폼·서비스를 **실제로 쓸지, 참고만 할지** (학생 실습 환경 부담이 크면 교육용 경량 구현)
- API 키 위치(.env), 나레이션 다듬기·TTS 모델
- 배포 대상(저장소 이름 규칙, 공개 여부) — 푸시 전 비밀 스캔 결과와 함께
