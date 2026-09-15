# 병렬 작성자 프롬프트 틀

공통 머리말 (모든 작성자):
```
You are writing <산출물> for a <과목> course. Everything must be grounded in a real, working system.
READ FIRST, fully: <작성 지침 경로> and <시스템 README>. Then read the relevant source and look at images you embed.
YOUR SCOPE: <반> sessions <n, m, k> — <세션별 한 줄 요약>.
DELIVERABLES: <파일 경로 규칙>, template §<n>, <분량>, ≥3 images (existing only), expected outputs from actually running.
VERIFY: <검증 명령> must pass; starters must fail (labs) / validator OK (specs). Report both.
HARD RULES: do not modify <시스템 폴더>. Do not reset/truncate databases, call reset endpoints, or restart servers
(others use them). Only write inside your own files. No invented numbers or fake outputs. <언어·문체>.
Final report (under 250 words): files, test results, any system facts that contradict the guide.
```

- 교재+실습: 회차 3개씩, 반별로 입문형/실전형 차이를 명시.
- 실습 영상 사양: 완성된 예시 사양 1편을 먼저 만들어 검증한 뒤 "match its depth, tone and structure" 로 제시. 회차별로 어울리는 app 장면 후보를 적어 준다.
- 결함 보고를 받으면: 시스템 수정 → `SendMessage` 로 해당 작성자에게 바뀐 동작(파일 경로 인용)을 알려 교재·실습 재동기화와 재검증을 요청.
