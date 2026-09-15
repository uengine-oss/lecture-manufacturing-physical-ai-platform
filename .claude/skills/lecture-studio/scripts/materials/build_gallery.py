"""materials/index.html — 중간 결과물 갤러리 (그림·개념도·실제 화면)."""
from pathlib import Path

M = Path(__file__).parent
ITEMS = [
 ("개념도", "diagrams/D01_architecture.png", "완성 시스템 아키텍처", "B1~B9 와 네 계층, 교육용 플랫폼 대응, 재측정 루프와 공통 연결 키", "실전반 1회 · 통합반 1회"),
 ("개념도", "diagrams/D02_event_path.png", "하나의 사건이 통과하는 경로", "감지부터 근거·승인·실행·재측정까지 같은 event_id", "실전반 1·8회 · 통합반 10회"),
 ("개념도", "diagrams/D07_storage.png", "저장소를 나누는 기준", "파일 / PostgreSQL / Neo4j 역할과 결합 키", "실전반 1·3회 · 통합반 2·3회"),
 ("데이터", "figures/F01_uci_1s_reduction.png", "B1 · 1초 공통 관측 형식", "100 Hz 압력·10 Hz 유량을 1초 평균·최솟값·최댓값으로 축약", "실전반 1회 · 통합반 1회"),
 ("데이터", "figures/F02_uci_cooler_states.png", "B1 · 냉각기 상태별 온도", "정답 라벨은 평가에만 — 100% 36°C · 20% 45°C · 3% 56°C", "실전반 1회 · 통합반 1회"),
 ("데이터", "figures/F03_quality_flags.png", "B2 · 품질 플래그", "원시 값 보존, 정제 값에서만 비움 — 결측·급등·고착", "실전반 2회 · 통합반 2회"),
 ("데이터", "figures/F08_neo4j_asset_graph.png", "B4 · 설비 관계 그래프", "설비마다 다른 SOP·허용 조치, 폐기 판은 점선", "실전반 3회 · 통합반 3회"),
 ("화면", "screenshots/S07_neo4j_browser_graph.png", "B4 · Neo4j Browser", "SOP–APPLIES_TO–Asset–HAS_SENSOR 경로 질의", "실전반 3회 · 통합반 3회"),
 ("데이터", "figures/F04_phase_baseline_residual.png", "B5 · 정상 위상 기준", "같은 위상끼리 비교하고 이동평균 잔차가 지속될 때만 이상", "실전반 4회 · 통합반 4회"),
 ("데이터", "figures/F05_detection_eval_compare.png", "B5 · 임계값과 지속 조건", "오탐은 허용 한계가 줄이고(4→1), 지속 조건은 임계값 근처 떨림을 거른다(99→0)", "실전반 4회 · 통합반 4회"),
 ("데이터", "figures/F10_zeroshot_vs_rules.png", "B5 선택 · zero-shot 예측 비교", "급변은 먼저 잡고, 처음부터 저하된 사이클은 놓친다", "실전반 4회 · 통합반 5회"),
 ("화면", "screenshots/S01_dashboard_normal.png", "B9 · 정상 운전", "사건 없음 — 조치 없음", "실전반 4회 · 통합반 4회"),
 ("화면", "screenshots/S02_dashboard_sensor_fault.png", "B9 · 센서 오류", "결측 → 센서 점검 제안, 설비 조치 보류", "실전반 4·5회 · 통합반 4회"),
 ("데이터", "figures/F09_sop_search_filter.png", "B6 · SOP 검색 필터", "설비·버전 필터가 근거의 범위를 정한다", "실전반 5회 · 통합반 5회"),
 ("개념도", "diagrams/D04_skill_sop_tool.png", "Skill · SOP · 도구", "업무 지침 / 문서 근거 / 실행 기능 + 도구 계약 표", "실전반 5·7회 · 통합반 5·6회"),
 ("화면", "screenshots/S06_dashboard_hold_no_evidence.png", "B7 · 근거 없음 보류", "SOP 가 없는 HYD-03 은 제안하지 않는다", "실전반 5회 · 통합반 6회"),
 ("화면", "screenshots/S03_dashboard_pending_approval.png", "B7·B8 · 승인 대기", "도구 호출 이력·SOP 인용·승인 폼", "실전반 5·7회 · 통합반 6회"),
 ("화면", "screenshots/S08_dashboard_rejected.png", "B8 · 승인 거부", "미실행 종료 — 실행 기록 없음", "실전반 7회 · 통합반 6회"),
 ("개념도", "diagrams/D03_state_flow.png", "B8 · 상태 흐름과 분기", "합격 목표 네 가지 0건", "실전반 7·8회 · 통합반 6·10회"),
 ("데이터", "figures/F06_closed_loop_same_seed.png", "B8 · 폐루프", "같은 시드에서 조치 유무 비교, 재측정 창", "실전반 8회 · 통합반 10회"),
 ("데이터", "figures/F07_verification_outcomes.png", "B8 · 재측정 세 갈래", "회복 · 미개선 · 데이터 부족", "실전반 8회 · 통합반 10회"),
 ("화면", "screenshots/S04_dashboard_closed.png", "B8·B9 · 회복 종결", "명령 성공과 회복 판정이 따로 남는다", "실전반 8회 · 통합반 10회"),
 ("화면", "screenshots/S05_dashboard_escalated.png", "B8 · 미개선 이관", "명령 SUCCEEDED 인데 회복 실패 → 이관", "실전반 8회 · 통합반 10회"),
 ("개념도", "diagrams/D05_local_vs_platform.png", "로컬과 플랫폼", "같은 서비스 함수를 LangGraph 와 플랫폼 프로세스가 부른다", "실전반 6회 · 통합반 7회"),
 ("화면", "screenshots/S10_platform_home.png", "교육용 플랫폼 · 개요", "네 계층 카드", "실전반 6회 · 통합반 7회"),
 ("화면", "screenshots/S11_platform_fabric.png", "Data Fabric", "사전 등록된 교육용 DB · 메타데이터 · 읽기 전용 질의", "실전반 6회 · 통합반 7회"),
 ("화면", "screenshots/S12_platform_studio_unpublished.png", "Ontology Studio · 발행 전", "매핑이 있어도 발행 전에는 조회 거부", "실전반 6회 · 통합반 7회"),
 ("화면", "screenshots/S13_platform_studio_published_golden.png", "Ontology Studio · 발행 후", "객체 조회와 Golden Question 3개", "실전반 6회 · 통합반 7회"),
 ("화면", "screenshots/S14_platform_agents_mcp_watch.png", "Agents · Skill · MCP · Watch", "허용 도구 4개, 조회 호출, 감시 에이전트로 업무 시작", "실전반 7회 · 통합반 8회"),
 ("화면", "screenshots/S15_platform_worklist_approval.png", "Process · 승인 태스크", "event_id·asset_id·run_id·제안값·근거가 폼에 매핑", "실전반 7회 · 통합반 8회"),
 ("화면", "screenshots/S16_platform_instance_closed.png", "Process · 인스턴스 기록", "업무 결과와 설비 재측정이 따로", "실전반 8회 · 통합반 8회"),
 ("화면", "screenshots/S17_platform_apps.png", "Apps · 게시 로그", "검증 → 번들 → 상태 확인 → 게시", "실전반 9회 · 통합반 9회"),
 ("화면", "screenshots/S18_app_ops_console.png", "게시된 제조 운영 앱", "화면·프로세스·조치 기록이 같은 사건 ✔✔✔", "실전반 9회 · 통합반 9·10회"),
 ("개념도", "diagrams/D06_roadmap.png", "회차별 블록 로드맵", "두 반의 회차 × B1~B9", "전 회차"),
]
cards = "".join(f'<figure class="c" data-k="{k}"><a href="{p}" target="_blank"><img loading="lazy" src="{p}"></a><figcaption><span class="tag t-{k}">{k}</span><b>{t}</b><p>{d}</p><small>{s}</small></figcaption></figure>' for k, p, t, d, s in ITEMS)
html = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HydOps 중간 결과물 갤러리</title>
<style>body{{margin:0;font-family:Pretendard,"Apple SD Gothic Neo",sans-serif;background:#f4f6f9;color:#18212f}}header{{background:#0f1b2d;color:#fff;padding:26px 34px}}h1{{margin:0;font-size:26px}}header p{{margin:6px 0 0;color:#b7c3d4}}
.f{{padding:14px 34px;display:flex;gap:8px}}.f button{{border:1px solid #cbd5e1;background:#fff;border-radius:99px;padding:6px 14px;font:inherit;cursor:pointer}}.f button.on{{background:#2a78d6;color:#fff;border-color:#2a78d6}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:18px;padding:0 34px 40px}}.c{{margin:0;background:#fff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden}}
.c img{{width:100%;height:240px;object-fit:contain;background:#fcfcfb;border-bottom:1px solid #eef1f5}}figcaption{{padding:12px 14px}}figcaption b{{font-size:16px}}figcaption p{{margin:4px 0;color:#475569;font-size:14px}}small{{color:#6941c6}}
.tag{{font-size:11.5px;border-radius:99px;padding:1px 9px;margin-right:8px}}.t-데이터{{background:#dbeafe;color:#1e40af}}.t-개념도{{background:#dcfce7;color:#166534}}.t-화면{{background:#fef3c7;color:#92400e}}</style>
<header><h1>HydOps 강의 — 중간 결과물 갤러리</h1><p>모든 그림은 실제 데이터·실제 실행으로 만들었다. 이미지를 누르면 원본 크기로 연다. 그림 재생성: <code>system/scripts/make_figures.py</code></p></header>
<div class="f"><button class="on" data-f="">전체</button><button data-f="데이터">데이터 그림</button><button data-f="개념도">개념도</button><button data-f="화면">실제 화면</button></div>
<div class="g">{cards}</div>
<script>document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.f button').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.c').forEach(c=>c.style.display=!b.dataset.f||c.dataset.k===b.dataset.f?'':'none')}})</script></html>"""
(M / "index.html").write_text(html)
missing = [p for _, p, *_ in ITEMS if not (M / p).exists()]
print("gallery items", len(ITEMS), "missing", missing)
