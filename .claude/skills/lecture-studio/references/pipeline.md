# 단계별 절차

## 0. 실라버스 분석
- `pandoc syllabus.docx -t markdown -o syllabus.md`, 그림은 `unzip -o syllabus.docx -d x && ls x/word/media`.
- 회차표를 그대로 옮긴다: 날짜·시간·모듈·원 일정 번호·블록(구현/확장/플랫폼)·네 단계 활동·산출물·완료 확인. 이 문구는 교재 메타 표에 **원문 그대로** 쓴다.
- 반이 여럿이면 반별 차이(학년·학생이 맡는 일·평가 제외 항목)를 표로 만든다.
- 금지 혼동 목록을 뽑는다 (예: 라벨 ≠ 제품 불량, 재생 시각 ≠ 수집 시각, 명령 성공 ≠ 회복, 업무 완료 ≠ 회복).

## 1. 완성 시스템
- 블록 이름·경계는 실라버스 아키텍처 그림을 따른다. 파일/모듈을 블록 번호로 나누면 교재가 쉬워진다 (`b1_data/`, `b2_quality/`…).
- 공개 데이터는 실제로 받아 특성을 먼저 측정한다(평균·주기·범위). 임계값은 "교육용 가정값"으로 명시하고, 가능하면 **측정한 정상 범위** 위에 둔다.
- 폐루프가 필요하면 조치에 반응하는 결정적 시뮬레이터(시드 고정)를 만든다. 원본 재생은 조치에 반응하지 않는다.
- LLM 에이전트는 두 모드를 둔다: 실제 LLM 과 같은 절차를 코드로 따르는 오프라인 모드(키 없음·장애 대비·결정적 테스트).
- 안전 규칙(승인 없는 실행 금지, 중복 실행 방지, 근거 없는 조치 보류)은 **도구 코드**에서 검사한다. 프롬프트/Skill 문서는 절차일 뿐이다.
- 외부 플랫폼이 참고만이면 같은 개념·API 모양의 교육용 경량 모듈(데이터소스 등록·온톨로지 발행·에이전트/Skill/MCP·프로세스/승인·앱 게시)을 한 서버로 만든다.
- 테스트 DB 는 공유 DB 와 분리한다(`<db>_test`). TRUNCATE 하는 테스트가 수업·시연 기록을 지운 적이 있다.
- Dockerfile/compose 로 학생 환경을 재현하고, 이미지 안에서 테스트 몇 개를 실제로 돌린다.

## 2. 실패 분기 리허설
- `scripts/e2e_*.py`: 사례별로 초기화 → 상황 주입 → 흐름 진행 → 최종 상태·기록 단정 → JSON 보고.
- 사례: 정상 회복, 승인 거부, 조치 후 미개선, 허용 범위 이탈, 도구 실패, 센서/데이터 문제, 중복 시작, 이미 처리된 사건 재처리.
- 리허설이 남긴 쓰레기(복제 정의 등)는 스크립트가 지운다 — 영상에 찍힌다.

## 3. 시각 자료
- 데이터 그림: `examples/hydops/make_figures.py` 패턴. 폰트(Pretendard 등 한글), 3계열 이하 팔레트, 그림마다 수치를 `figures_data.json` 에 남긴다. **그림 제목의 주장(“A 가 B 를 줄였다”)은 변수 하나씩 바꾼 격자로 확인**한 뒤 쓴다.
- 개념도: HTML(`#d` 요소) → `scripts/explainer/render_diagrams.mjs src out` (2배 해상도). 라벨 겹침은 `paint-order:stroke` 로 해결.
- 실제 화면: Playwright 로 상태를 연출하고 `data-testid` 로 DOM 단정 후 캡처. 로그인 폼·자동완성 팝업·다른 포트 인스턴스에 주의.
- `scripts/materials/build_gallery.py` 로 갤러리(용도·회차 표시).

## 4. 설명 영상
- 대본 `narration.json` [{scene, title, text}] — 도메인 사건으로 시작, 장면당 20~35초, 숫자는 읽히는 대로. `scripts/explainer/check_narration.py`.
- TTS: `gen_narration_openai.py --script narration.json --out-dir narration --voice marin --env-file .env`.
- 녹화: `examples/hydops/record_explainer_video.mjs` 패턴 — 슬라이드(실제 그림 base64) + 실제 앱 조작, 장면마다 `hold(나레이션 길이)`, `assertText` 로 화면 단정, 실패 시 `FAIL-*.png` 남기고 중단. 모드 전환(서버 재시작)은 슬라이드 장면 동안 백그라운드로.
- 합성: `EXPLAINER_DIR=... VIDEO_TITLE=... python scripts/explainer/finish_video.py` — 겹침 표, 소프트 자막(mov_text), 음량·디코드 검사.
- **원본 해상도 프레임을 반드시 본다** (§lessons 1).

## 5. 교재·실습
- 먼저 `textbooks/_AUTHORING_GUIDE.md` 를 쓴다 (예: `examples/hydops/textbook_authoring_guide.md`): 반 차이, 시스템 사실표(파일·함수·API), 확인된 수치, 실제로 드러난 문제(흔한 실수 소재), 표현 금지 목록, 그림 목록, 템플릿, 회차표 원문, 실습 규칙.
- 교재 템플릿: 메타 표 → 할 일·학습 목표 → 시작 전 준비(명령+실제 출력) → 핵심 개념(그림) → 활동 1~4(목표·따라 하기·확인 포인트·흔한 실수) → 실습 과제 → 완료 확인 체크리스트 → 회고 → 실제 플랫폼 대응 → 강사 노트 → 용어.
- 실습: `TASK.md` · 시작본(실전형은 `# TODO` 틀린 로직, 입문형은 `____` 빈칸) · `solution/` · `test_check.py`(`LAB_SOLUTION=1` 이면 정답 검사). **정답 통과·시작본 실패**를 전 회차 루프로 확인하고 결과 파일로 남긴다. 실패 판정 grep 은 `failed|error` 를 봐야 한다(`passed in` 제외 grep 은 "1 failed, 15 passed in" 을 놓친다).
- 빌드: `LECTURE_ROOT=. python scripts/textbooks/build_textbooks.py --pdf` — 첫 H1 을 제목 메타데이터로 옮겨 제목 중복 방지, 참조 docx 로 한글 폰트.

## 6. 실습 영상
### 6-1. 사양
`references/lab-video-spec-guide.md` 스키마. 구성 고정: title → 개념(4~7) → 실습(task·code·run·apply_fix·app) → quiz(3) → answer(3) → summary → next.
- 실습은 **시작본 run(fail) → 함수 하나씩 apply_fix(function) → run → … → run(pass)**. 실패 수가 줄어드는 과정이 보이게.
- 출력만 보여 주는 스크립트는 `demo: true`(배지 '실행 완료'), 검사기 스크립트는 pass/fail 배지 유지.
- 마지막 회차의 `next` 는 과정 마무리(발표·제출물·평가 기준).
### 6-2. 제작
`validate_spec.py <ID> --run` 이 OK 여야 한다 → `produce.sh`. 렌더는 `labs_work/<반>/<회차>` 작업 사본에서 실제 실행을 녹화하고, 기대와 다르면 즉시 중단한다. 앱 장면은 잠금 파일로 직렬화된다.
### 6-3. 기초 보강판
기존 사양 보관 → 부 구조·복습 장면·`explain`·`snippet/output`·`demos/` 실행 시연·정답 코드 재독 → `target_minutes`·`polish_ratio` 로 길이 조정. 시연 번호가 장면 삭제로 비지 않게 확인.
### 6-4. 검수
`sheet.py <ID>` 프레임 모음 + 의심 장면은 **원본 해상도로 한 장** 뽑아 본다. `final_report.json` 의 runs·app_checks·decode·음량 확인 → `index.py`.

## 7. 배포
- `.gitignore`: 가상환경, node_modules, 녹화 원본(webm), 장면 클립(build/), 작업 사본(labs_work/), 게시 앱 사본.
- 비밀 스캔: `sk-(proj|live)-…`, `OPENAI_API_KEY=…`, `gho_…`, `.env` 파일.
- 저장소가 이미 있거나 다른 세션이 푸시 중이면 **이름 변경/새 저장소/그대로** 중 사용자에게 묻는다. 삭제·보관은 하지 않는다.
- 파일당 100MB 미만 확인(영상은 편당 30~45MB 였다).
