# 사례 — 제조 피지컬 AI · 플랫폼 연계 교육과정 (2026-09)

- 저장소: github.com/uengine-oss/lecture-manufacturing-physical-ai-platform
- 실라버스: 유압설비 냉각 이상 감지 → 설비 관계·SOP 근거 → 사람 승인 → 시뮬레이터 조치 → 재측정. B1~B9 블록, 실전반 9회·통합반 10회.
- 시스템: PostgreSQL+Neo4j, UCI hydraulic 데이터, 상태 시뮬레이터, 품질 플래그, 규칙·위상 기준 탐지, Neo4jVector SOP 검색, LangChain 에이전트+SKILL.md, LangGraph 승인·재측정, FastAPI+Vue 관제, MCP 도구 6종, 교육용 플랫폼(Data Fabric·Ontology Studio·Agents·Process·Apps 대응).
- 검증: 시스템 테스트 25, LLM 시나리오 18, 플랫폼 E2E 7/7, 실습 19개 정답 통과·시작본 실패, 실습 영상 실행 장면 70개 기대 일치.
- 산출물: 설명 영상 7분 6초(17장면), 그림 10·개념도 7·화면 17, 교재 19편(DOCX·HTML·PDF 11~23쪽), 실습 영상 19편 4시간 10분(편당 12~14분), 기초 보강판 실전반 1회 약 26분(49장면, 시연 3종 실제 실행).
- 예시 파일: `examples/hydops/` — 작성 지침, 그림 스크립트, 설명 영상 녹화·대본, 실습 영상 사양(표준·보강), 문법 시연 스크립트.
