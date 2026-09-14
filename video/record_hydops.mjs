// HydOps 강의 시스템 설명 영상 녹화 — 슬라이드(실제 그림) + 실제 실행 화면
// 사용: node record_hydops.mjs            (본 녹화)
//       FAST=1 node record_hydops.mjs     (나레이션 대기만 줄인다 — 화면 검증은 그대로)
import { chromium } from 'playwright';
import { exec } from 'child_process';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

const sh = promisify(exec);
const FAST = !!process.env.FAST;
const LECTURE = '/Users/uengine/uengine-platform/lecture';
const SYS = `${LECTURE}/system`;
const WORK = `${LECTURE}/video/work`;
const H = 'http://localhost:8800', P = 'http://localhost:8910';
const DUR = Object.fromEntries(JSON.parse(fs.readFileSync(`${WORK}/narration/durations.json`)).map(d => [d.scene, d.duration]));
const NAR = Object.fromEntries(JSON.parse(fs.readFileSync(`${WORK}/narration.json`)).map(d => [d.scene, d]));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = (base, u, body) => fetch(base + u, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined).then(r => r.json());
const img = p => `data:image/png;base64,${fs.readFileSync(`${LECTURE}/materials/${p}`).toString('base64')}`;
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

async function waitFor(fn, ms, what) {
  const t = Date.now();
  while (Date.now() - t < ms) { const v = await fn().catch(() => null); if (v) return v; await sleep(600); }
  throw new Error('timeout: ' + what);
}

// ---- 페이지 헬퍼: 자막 바 · 스포트라이트 -------------------------------------------------
const HELPERS = () => {
  const ensure = () => {
    if (document.getElementById('vo-cap')) return;
    const st = document.createElement('style');
    st.textContent = `#vo-cap{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;background:rgba(9,17,31,.92);color:#fff;
      font:600 17px Pretendard,"Apple SD Gothic Neo",sans-serif;padding:9px 20px;border-radius:999px;box-shadow:0 8px 30px rgba(0,0,0,.35);white-space:nowrap}
      #vo-cap b{color:#7dd3fc;margin-right:10px}
      .vo-spot{position:fixed;z-index:99998;border:3px solid #f59e0b;border-radius:12px;box-shadow:0 0 0 9999px rgba(15,23,42,.28),0 0 24px #f59e0b;pointer-events:none;transition:all .35s ease}
      #vo-inset{position:fixed;z-index:99997;right:26px;top:90px;width:560px;border-radius:12px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.45);border:3px solid #ef4444;background:#fff}
      #vo-inset div{background:#ef4444;color:#fff;font:700 15px Pretendard,sans-serif;padding:6px 12px}#vo-inset img{width:100%;display:block}`;
    document.head.appendChild(st);
    const cap = document.createElement('div'); cap.id = 'vo-cap'; cap.style.display = 'none'; document.body.appendChild(cap);
  };
  window.__cap = (n, t) => { ensure(); const c = document.getElementById('vo-cap'); c.style.display = t ? 'block' : 'none'; c.innerHTML = `<b>${n}</b>${t}`; };
  window.__spot = (sel) => {
    ensure(); clearInterval(window.__spotTimer); document.querySelectorAll('.vo-spot').forEach(e => e.remove());
    if (!sel) return;
    const box = document.createElement('div'); box.className = 'vo-spot'; document.body.appendChild(box);
    const place = () => { const el = document.querySelector(sel); if (!el) { box.style.opacity = 0; return; } const r = el.getBoundingClientRect(); Object.assign(box.style, { opacity: 1, left: r.left - 6 + 'px', top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px' }); };
    place(); window.__spotTimer = setInterval(place, 250);
  };
  window.__inset = (src, label) => { ensure(); document.getElementById('vo-inset')?.remove(); if (!src) return; const d = document.createElement('div'); d.id = 'vo-inset'; d.innerHTML = `<div>${label}</div><img src="${src}">`; document.body.appendChild(d); };
};

// ---- 녹화 ------------------------------------------------------------------------------
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1536, height: 864 }, recordVideo: { dir: `${WORK}/raw`, size: { width: 1920, height: 1080 } } });
await ctx.addInitScript(HELPERS);
const page = await ctx.newPage();
const T0 = Date.now();
const timing = [];
const checks = [];
let sceneStart = 0;

async function fail(msg) {
  await page.screenshot({ path: `${WORK}/FAIL-${Date.now()}.png` });
  console.error('FAIL', msg);
  await ctx.close(); await browser.close(); process.exit(1);
}
async function assertText(sel, re, label) {
  const txt = await page.$eval(sel, e => e.innerText).catch(() => '');
  if (!re.test(txt)) await fail(`${label}: ${sel} → ${txt.slice(0, 200)}`);
  checks.push(`✓ ${label}`);
}
async function mainLen(min, label) {
  const n = await page.evaluate(() => document.body.innerText.length);
  if (n < min) await fail(`${label}: body ${n}자`);
  checks.push(`✓ ${label}(${n}자)`);
}
async function scene(n) {
  sceneStart = Date.now();
  timing.push({ scene: n, start_sec: +((sceneStart - T0) / 1000).toFixed(2), title: NAR[n].title });
  log(`scene ${n} ${NAR[n].title}`);
}
async function hold(n, pad = 1.2) {
  const need = FAST ? 1500 : (DUR[n] + pad) * 1000;
  const left = need - (Date.now() - sceneStart);
  if (left > 0) await sleep(left);
}
const cap = (t) => page.evaluate(([n, t]) => window.__cap?.(n, t), [`${timing.length ? timing[timing.length - 1].scene : ''}`, t]);
const spot = (sel) => page.evaluate(s => window.__spot?.(s), sel);
const scrollTo = async (sel, block = 'start') => { await page.evaluate(([s, b]) => document.querySelector(s)?.scrollIntoView({ behavior: 'smooth', block: b }), [sel, block]); await sleep(900); };

async function slide({ kicker, title, body = '', images = [], layout = 'stack', foot = '' }) {
  const imgs = images.map(i => `<figure style="flex:${i.flex || 1}"><img src="${img(i.src)}"/>${i.cap ? `<figcaption>${i.cap}</figcaption>` : ''}</figure>`).join('');
  await page.setContent(`<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
  *{box-sizing:border-box}body{margin:0;background:#0b1422;font-family:Pretendard,"Apple SD Gothic Neo",sans-serif;color:#eef4fb}
  .s{height:864px;padding:34px 48px 40px;display:flex;flex-direction:column;background:radial-gradient(circle at 92% 0%,#17365c 0,transparent 38%),linear-gradient(135deg,#0b1422,#101d31)}
  .k{color:#7dd3fc;font-weight:800;letter-spacing:.06em;font-size:15px}.t{font-size:36px;font-weight:800;letter-spacing:-.02em;margin:8px 0 6px}
  .b{font-size:18px;color:#b6c5d8;line-height:1.55;max-width:1380px;margin-bottom:14px}
  .imgs{flex:1;display:flex;gap:16px;min-height:0;flex-direction:${layout === 'row' ? 'row' : 'column'};align-items:center;justify-content:center}
  figure{margin:0;min-height:0;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#fcfcfb;border-radius:14px;padding:10px;max-height:100%;width:100%}
  figure img{max-width:100%;max-height:100%;object-fit:contain;display:block;min-height:0}figcaption{color:#475569;font-size:13px;margin-top:4px}
  .f{display:flex;justify-content:space-between;color:#64748b;font-size:13px;margin-top:10px}
  </style></head><body><div class="s"><div class="k">${kicker}</div><div class="t">${title}</div><div class="b">${body}</div><div class="imgs">${imgs}</div>
  <div class="f"><span>제조 피지컬 AI · 플랫폼 연계 교육과정 — 완성 시스템</span><span>${foot}</span></div></div></body></html>`);
}

try {
  // 준비: 로컬 모드, 깨끗한 실행
  log('servers → local');
  await sh(`${SYS}/scripts/servers.sh local 4`);
  await api(H, '/api/control', { reset: true, seed: 42 });

  // 1 사건 하나
  await scene(1);
  await slide({ kicker: '01 · 사건 하나', title: '온도가 60°C 를 넘었다 — 무엇을 확인해야 사건을 닫을 수 있나', body: '센서 오류인가 설비 이상인가 → 어떤 매뉴얼이 허용하나 → 누가 승인했나 → 조치 후 새 관측은 회복했나', images: [{ src: 'diagrams/D02_event_path.png' }], foot: '하나의 사건이 통과하는 경로' });
  await hold(1);

  // 2 데이터
  await scene(2);
  await slide({ kicker: '02 · Data Sources · B1', title: '주기가 다른 세 센서를 1초 공통 관측 형식으로', body: 'UCI 유압설비 데이터 2,205 사이클 × 60초 · 냉각기 100% ≈ 36°C · 20% ≈ 45°C · 3% ≈ 56°C — 정답 라벨은 평가에만 쓴다', images: [{ src: 'figures/F01_uci_1s_reduction.png', flex: 1 }, { src: 'figures/F02_uci_cooler_states.png', flex: 1.25 }], foot: '실제 데이터로 그린 그림' });
  await hold(2);

  // 3 품질
  await scene(3);
  await slide({ kicker: '03 · Data Sources · B2', title: '센서 오류와 설비 이상을 구분한다', body: '원시 값은 보존하고 정제 값에서만 비운다 · 5초 넘는 결측(GAP)과 고착(STUCK)은 판정 보류', images: [{ src: 'figures/F03_quality_flags.png' }], foot: '오류 주입본 사이클 #1500 — OK 49 · MISSING 4 · GAP 3 · SPIKE 1 · STUCK 3' });
  await hold(3);

  // 4 온톨로지
  await scene(4);
  await slide({ kicker: '04 · Ontology · B4 + B6', title: '설비 · 센서 · 매뉴얼 · 허용 조치의 관계', body: 'HYD-01 → 부하 감소 · HYD-02 → 팬 증속 · HYD-03 → 적용 SOP 없음(근거 없음 보류) · 시계열은 그래프에 넣지 않는다', images: [{ src: 'figures/F08_neo4j_asset_graph.png' }], foot: 'Neo4j 에 실제로 적재된 그래프' });
  await hold(4);

  // 5 관제 화면 (실제 실행)
  await scene(5);
  await page.goto(H);
  await page.waitForSelector('[data-testid=chart]');
  await sleep(1500);
  await mainLen(500, '관제 화면 렌더');
  await assertText('[data-testid=mode]', /로컬/, '로컬 오케스트레이션 모드');
  await cap('관제 화면 · 정상 운전 — 사건 없음');
  await spot('.chart'); await sleep(FAST ? 800 : 7000);
  await spot('.assets'); await sleep(FAST ? 800 : 5000);
  await spot('.inject');
  await hold(5);
  await spot(null);

  // 6 센서 결측
  await scene(6);
  await cap('센서 결측 주입 → 품질 플래그 → 센서 오류 사건');
  await page.click('[data-testid=inject-dropout]');
  await spot('.chart');
  const sf = await waitFor(async () => (await api(H, '/api/events')).find(e => e.event_type === 'SENSOR_FAULT' && ['SENSOR_CHECK', 'HOLD_NO_EVIDENCE'].includes(e.status)), 90000, 'sensor fault handled');
  await page.click(`[data-testid="status-${sf.event_id}"]`);
  await sleep(1200);
  await scrollTo('.detail');
  await assertText('[data-testid=decision]', /센서 점검/, '센서 오류 → 센서 점검 제안');
  await spot('[data-testid=decision]'); await sleep(FAST ? 800 : 3500);
  await spot('.detail .cols .card:nth-child(2)');
  await hold(6);
  await spot(null);

  // 7 냉각 성능 저하
  await scene(7);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(700);
  await cap('냉각 성능 40% 주입 → 유효 관측 60°C 초과 10초 지속');
  await page.click('[data-testid=inject-cooling]');
  await spot('.chart');
  const ev = await waitFor(async () => (await api(H, '/api/events')).find(e => e.event_type === 'COOLING_ANOMALY'), 120000, 'cooling event');
  await sleep(1000);
  await spot('.events');
  await hold(7, 0.5);

  // 8 에이전트
  await scene(8);
  await cap('운영 에이전트 · 도구 호출 → SOP 인용 → 허용 범위 검사');
  await page.click(`[data-testid="status-${ev.event_id}"]`);
  await scrollTo('.detail');
  await spot('.detail .cols .card:nth-child(2)');
  await page.waitForSelector('[data-testid=approval-form]', { timeout: 120000 }).catch(() => fail('승인 폼이 나타나지 않음'));
  await sleep(800);
  const tools = await page.$$eval('[data-testid=tool-call]', els => els.map(e => e.innerText.split('\n')[0]));
  if (!tools.includes('search_sop') || !tools.includes('propose_action')) await fail('도구 호출 이력 부족 ' + tools);
  checks.push(`✓ 에이전트 도구 호출 ${tools.join('→')}`);
  await assertText('[data-testid=decision]', /조치 제안.*REDUCE_LOAD/s, '부하 감소 제안');
  const cites = await page.$$eval('[data-testid=citation]', els => els.length);
  if (cites < 1) await fail('인용 없음'); checks.push(`✓ SOP 인용 ${cites}건`);
  await sleep(FAST ? 500 : 4000);
  await spot('[data-testid=citation]'); await sleep(FAST ? 500 : 4000);
  await spot('[data-testid=approval-form]');
  await hold(8);

  // 9 승인과 실행
  await scene(9);
  await cap('사람의 승인 → 실행 도구가 승인 기록을 검사한 뒤 명령');
  await spot('[data-testid=approval-form]'); await sleep(FAST ? 600 : 5000);
  await page.click('[data-testid=approve]');
  await page.waitForSelector('[data-testid=action-log]', { timeout: 30000 }).catch(() => fail('실행 기록 없음'));
  await assertText('[data-testid=action-log]', /SUCCEEDED/, '명령 성공 기록');
  await spot('[data-testid=action-log]'); await sleep(FAST ? 600 : 3500);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(900);
  await spot('.chart');
  await hold(9);

  // 10 재측정·종결
  await scene(10);
  await cap('조치 30초 후 60초 재측정 창 · 55°C 이하 10초 유지 → 종결');
  await spot('.chart');
  await waitFor(async () => (await api(H, `/api/events/${ev.event_id}`)).event.status === 'CLOSED', 150000, 'closed');
  await sleep(1500);
  await scrollTo('.detail');
  await assertText('[data-testid=verification]', /회복/, '재측정 회복 판정');
  await assertText('[data-testid=flow]', /종결/, '흐름 종결');
  await spot('[data-testid=flow]'); await sleep(FAST ? 600 : 3000);
  await spot('.detail .cols .card:nth-child(4)'); await sleep(FAST ? 600 : 5000);
  await spot('.detail .cols2');
  await hold(10);
  await spot(null);

  // 11 분기 (슬라이드) — 이 동안 플랫폼 모드로 전환
  await scene(11);
  const switching = sh(`${SYS}/scripts/servers.sh platform 4`);
  await slide({ kicker: '11 · Orchestration · B8', title: '같은 조치, 다른 결과 — 분기는 기록으로 남는다', body: '미개선 → 이관·반복 억제 · 재측정 중 센서 결측 → 판정 보류 · 합격 목표: 근거 없는 조치 0 · 승인 없는 실행 0 · 중복 실행 0 · 재측정 없는 종결 0', images: [{ src: 'figures/F07_verification_outcomes.png', flex: 1 }, { src: 'diagrams/D03_state_flow.png', flex: 1.1 }], foot: '시뮬레이터 실제 실행 결과' });
  await hold(11);

  // 12 평가
  await scene(12);
  await slide({ kicker: '12 · Agents · B5', title: '임계값과 지속 조건은 하는 일이 다르다', body: 'UCI 시험 구간: 허용 한계 1°C→3°C 가 오탐 4→1, 지속 1→10초는 오탐 그대로·지연 +9초 · 시뮬레이터 59.8°C 떨림: 지속 1초 99회 → 5초 0회 · zero-shot: 급변은 먼저(t=64 vs 82), 처음부터 저하된 사이클은 0/60', images: [{ src: 'figures/F05_detection_eval_compare.png', flex: 0.8 }, { src: 'figures/F10_zeroshot_vs_rules.png', flex: 1.05 }], foot: 'UCI 고정 시험 180 사이클 · Chronos-Bolt tiny' });
  await switching;
  await waitFor(async () => (await api(H, '/api/state')).mode === 'platform', 30000, 'platform mode');
  checks.push('✓ 플랫폼 오케스트레이션 모드 전환');
  await hold(12);

  // 13 플랫폼 지식 계층
  await scene(13);
  await page.goto(`${P}/console/#studio`);
  await page.waitForSelector('[data-testid=class-table]');
  await mainLen(800, 'Ontology Studio 렌더');
  await cap('교육용 플랫폼 · Ontology Studio — 매핑 → 발행 → 조회 → Golden Question');
  await page.evaluate(([s]) => window.__inset(s, '발행 전: 객체 조회 거부 (409)'), [img('screenshots/S12_platform_studio_unpublished.png')]);
  await spot('[data-testid=publish-state]'); await sleep(FAST ? 800 : 5000);
  await page.evaluate(() => window.__inset(null));
  await assertText('[data-testid=publish-state]', /발행 v\d/, '스키마 발행됨');
  await spot('[data-testid=class-table]'); await sleep(FAST ? 600 : 4000);
  await page.click('[data-testid=fetch]'); await page.waitForSelector('[data-testid=objects]');
  await spot('[data-testid=objects]'); await sleep(FAST ? 600 : 3000);
  await page.click('[data-testid=golden]'); await page.waitForSelector('[data-testid=golden-row]');
  await sleep(1200);
  const golden = await page.$$eval('[data-testid=golden-row]', els => els.map(e => e.classList.contains('good')));
  checks.push(`✓ Golden Question ${golden.filter(Boolean).length}/${golden.length}`);
  await spot('[data-testid=golden-row]');
  await hold(13);

  // 14 업무 에이전트·Watch
  await scene(14);
  await api(H, '/api/control', { reset: true, seed: 42 });
  await sleep(1500);
  await api(H, '/api/sim/HYD-01/inject', { kind: 'cooling' });
  await page.click('[data-testid=tab-agents]');
  await page.waitForSelector('[data-testid=mcp-tool]', { timeout: 30000 });
  await cap('업무 에이전트 · 할당 Skill + 허용 도구 4개 · Watch Agent 가 사건 한 건으로 업무 시작');
  await spot('[data-testid=agent]'); await sleep(FAST ? 600 : 5500);
  await spot('.toollist'); await sleep(FAST ? 600 : 3500);
  const ev2 = await waitFor(async () => (await api(H, '/api/events')).find(e => e.event_type === 'COOLING_ANOMALY' && e.status === 'DETECTED'), 120000, 'platform event');
  await page.click('[data-testid=watch-tick]'); await sleep(1500);
  await assertText('.note', /fired=true.*시작 PI-/s, 'Watch → 업무 시작');
  await spot('.watch');
  await hold(14);

  // 15 승인 태스크
  await scene(15);
  await page.click('[data-testid=tab-process]');
  await cap('워크리스트 · 조치 승인 태스크 — 사건 ID·설비·실행 ID·제안값·근거가 폼에 매핑');
  await spot('.card:has([data-testid=instance])');
  await page.waitForSelector('[data-testid=workitem]', { timeout: 180000 }).catch(() => fail('승인 태스크 도착 안 함'));
  await sleep(1000);
  await assertText('[data-testid=workitem]', new RegExp(ev2.event_id), '폼에 event_id 보존');
  await assertText('[data-testid=ro-action_id]', /REDUCE_LOAD/, '제안 조치 매핑');
  await spot('[data-testid=workitem]'); await sleep(FAST ? 800 : 7000);
  await page.fill('[data-testid=f-approver]', 'kim.operator');
  await spot('[data-testid=complete]'); await sleep(FAST ? 400 : 2000);
  await page.click('[data-testid=complete]');
  await sleep(1500);
  await page.click('[data-testid=instance]'); await page.waitForSelector('[data-testid=instance-detail]');
  await scrollTo('[data-testid=instance-detail]', 'start');
  await spot('[data-testid=instance-detail]');
  await hold(15);
  const inst = await waitFor(async () => (await api(P, '/process/instances')).find(i => i.event_id === ev2.event_id && i.status !== 'RUNNING'), 240000, 'instance done');
  if (inst.equipment_outcome !== 'RECOVERED') await fail('설비 회복 아님 ' + JSON.stringify(inst));
  checks.push(`✓ 인스턴스 ${inst.instance_id} COMPLETED · 설비 RECOVERED`);

  // 16 업무 완료 · 앱
  await scene(16);
  await cap('업무 결과(종결)와 설비 재측정(RECOVERED)은 따로 기록된다');
  await sleep(2500);
  await scrollTo('[data-testid=instance-detail]', 'start');
  await spot('[data-testid=instance-detail] .row'); await sleep(FAST ? 800 : 6000);
  await page.goto(`${P}/apps/hydops-ops/`);
  await page.waitForSelector('[data-testid=app-event]', { timeout: 30000 });
  await page.click('[data-testid=app-event]');
  await page.waitForSelector('[data-testid=app-detail]');
  await sleep(3000);
  await cap('게시한 제조 운영 앱 · 화면 · 업무 입력 · 조치 기록이 같은 사건');
  await assertText('[data-testid=same-event]', /✔ 화면.*✔ 프로세스.*✔ 조치/s, '같은 사건 3중 확인');
  await spot('[data-testid=same-event]');
  await hold(16);
  await spot(null);

  // 17 마무리
  await scene(17);
  await slide({ kicker: '17 · 과정 구성', title: '센서 값 하나에서 근거 · 승인 · 재측정이 남는 운영 판단까지', body: '실전반 9회: 함수·질의·정책 수정과 검증 · 통합반 10회: 매핑·설정·조건 완성 · 회차별 교재 19권 · 실습 과제와 정답 검증 테스트', images: [{ src: 'diagrams/D06_roadmap.png' }], foot: 'lecture/system · lecture/textbooks · lecture/labs' });
  await hold(17, 2.5);
} catch (e) {
  await fail(e.message);
}

const videoPath = await page.video().path();
await ctx.close(); await browser.close();
const raw = `${WORK}/raw/hydops-raw${FAST ? '-fast' : ''}.webm`;
fs.renameSync(videoPath, raw);
fs.writeFileSync(`${WORK}/scenes-timing${FAST ? '-fast' : ''}.json`, JSON.stringify(timing, null, 2));
fs.writeFileSync(`${WORK}/checks${FAST ? '-fast' : ''}.txt`, checks.join('\n') + '\n');
console.log(checks.join('\n'));
console.log('raw', raw, 'total', ((Date.now() - T0) / 1000).toFixed(1), 's');
