// [도메인별로 고쳐 쓰는 파일] 실습 영상의 실제 화면 조작 — render.mjs 의 app 장면이 부른다.
// 아래 동작(dashboard·console·platform_flow…)은 HydOps 강의 예시다. 새 강의에서는 그 강의의 앱 URL·선택자·서버 기동 명령으로 바꾼다.
// 공유 서버(관제 :8800, 플랫폼 :8910)를 쓰므로 프로세스 사이에 잠금(mkdir)을 건다.
import { exec, execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

const sh = promisify(exec);
const H = process.env.APP_API || 'http://localhost:8800', P = process.env.PLATFORM_API || 'http://localhost:8910';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const api = (base, u, body) => fetch(base + u, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined).then(r => r.json());
const SPEED = 8;

async function waitFor(fn, ms, what) {
  const t = Date.now();
  while (Date.now() - t < ms) { const v = await fn().catch(() => null); if (v) return v; await sleep(700); }
  throw new Error('timeout: ' + what);
}

async function lock(dir) {
  for (;;) {
    try { fs.mkdirSync(dir); return () => fs.rmSync(dir, { recursive: true, force: true }); } catch { await sleep(1000); }
  }
}

async function ensureMode(SYSTEM, mode) {
  const st = await api(H, '/api/state').catch(() => null);
  const plat = await fetch(P + '/health').then(r => r.ok).catch(() => false);
  if (st && st.mode === mode && st.speed === SPEED && plat) return;
  await sh(`${SYSTEM}/scripts/servers.sh ${mode} ${SPEED}`);
}

const OVERLAY = ({ cap, secs, on, badge, title }) => {
  const st = document.createElement('style');
  st.textContent = `#lv-top{position:fixed;left:0;right:0;top:0;z-index:99999;display:flex;gap:10px;align-items:center;padding:8px 18px;background:rgba(9,17,31,.9);font:600 14px Pretendard,sans-serif;color:#cbd5e1}
  #lv-top b{background:#1d4ed8;color:#fff;border-radius:7px;padding:3px 10px}#lv-top .sp{flex:1}#lv-top .s{padding:3px 10px;border-radius:99px;background:rgba(255,255,255,.08);font-size:12px}#lv-top .s.on{background:#f59e0b;color:#1a1300}
  #lv-cap{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:99999;background:rgba(4,10,20,.9);color:#fff;font:700 20px Pretendard,sans-serif;padding:9px 24px;border-radius:99px;white-space:nowrap}
  .lv-spot{position:fixed;z-index:99998;border:3px solid #f59e0b;border-radius:12px;box-shadow:0 0 0 9999px rgba(15,23,42,.25),0 0 24px #f59e0b;pointer-events:none;transition:all .35s}
  body{padding-top:36px !important}`;
  document.head.appendChild(st);
  const top = document.createElement('div'); top.id = 'lv-top';
  top.innerHTML = `<b>${badge}</b><span>${title}</span><span class="sp"></span>` + secs.map(s => `<span class="s ${s === on ? 'on' : ''}">${s}</span>`).join('');
  document.body.appendChild(top);
  if (cap) { const c = document.createElement('div'); c.id = 'lv-cap'; c.textContent = cap; document.body.appendChild(c); }
  window.__spot = (sel) => {
    clearInterval(window.__st); document.querySelectorAll('.lv-spot').forEach(e => e.remove()); if (!sel) return;
    const box = document.createElement('div'); box.className = 'lv-spot'; document.body.appendChild(box);
    const place = () => { const el = document.querySelector(sel); if (!el) { box.style.opacity = 0; return; } const r = el.getBoundingClientRect(); Object.assign(box.style, { opacity: 1, left: r.left - 6 + 'px', top: r.top - 6 + 'px', width: r.width + 12 + 'px', height: r.height + 12 + 'px' }); };
    place(); window.__st = setInterval(place, 250);
  };
};

export async function runApp(page, sc, ctx) {
  const { total, spec, sectionMap, i, SECTIONS, LECTURE, SYSTEM } = ctx;
  const tStart = Date.now();
  const checks = [];
  const overlayArgs = { cap: sc.caption || '', secs: SECTIONS, on: sectionMap[i - 1], badge: `${spec.class} ${spec.session}회`, title: spec.title };
  const decorate = async () => { await page.evaluate(OVERLAY, overlayArgs).catch(() => {}); };
  const spot = sel => page.evaluate(s => window.__spot?.(s), sel).catch(() => {});
  const holdRest = async (min = 1500) => { const left = total * 1000 - (Date.now() - t0); await sleep(Math.max(min, left)); };
  const pr = sc.params || {};
  const release = ['dashboard', 'console', 'platform_flow', 'app_page'].includes(sc.action) ? await lock(path.join(process.env.LAB_VIDEOS_DIR || path.join(LECTURE, 'video/lab_videos'), 'build/.app.lock')) : () => {};
  const t0 = Date.now();  // 잠금을 기다린 시간은 영상 앞에서 잘라 낸다
  try {
    switch (sc.action) {
      case 'dashboard': {
        await ensureMode(SYSTEM, 'local');
        await api(H, '/api/control', { reset: true, seed: 42 });
        await page.goto(H); await page.waitForSelector('[data-testid=chart]'); await decorate();
        const asset = pr.asset || 'HYD-01';
        if (asset !== 'HYD-01') await page.click(`[data-testid=asset-${asset}]`);
        await sleep(2500);
        await spot(pr.focus === 'events' ? '.events' : '.chart');
        if (!pr.inject) { await sleep(Math.min(8000, total * 400)); await spot('.inject'); break; }
        await sleep(1500);
        await api(H, `/api/sim/${asset}/inject`, { kind: pr.inject });
        checks.push(`inject ${pr.inject} ${asset}`);
        const etype = ['dropout', 'stuck'].includes(pr.inject) ? 'SENSOR_FAULT' : 'COOLING_ANOMALY';
        if (pr.inject === 'spike') { await sleep(9000); const evs = await api(H, '/api/events'); checks.push(`spike events=${evs.length}`); break; }
        const ev = await waitFor(async () => (await api(H, '/api/events')).find(e => e.asset_id === asset && e.event_type === etype), 90000, 'event');
        await spot('.events');
        const settled = await waitFor(async () => { const e = (await api(H, `/api/events/${ev.event_id}`)).event; return e.status !== 'DETECTED' && e.status !== 'EVIDENCE_READY' ? e : null; }, 120000, 'evidence');
        await page.click(`[data-testid="status-${ev.event_id}"]`); await sleep(1200);
        await page.evaluate(() => document.querySelector('.detail')?.scrollIntoView({ behavior: 'smooth' })); await sleep(900);
        await spot('.detail .cols .card:nth-child(2)');
        checks.push(`status ${settled.status}`);
        if (settled.status === 'PENDING_APPROVAL' && pr.decision && pr.decision !== 'none') {
          await sleep(4000);
          await page.waitForSelector('[data-testid=approval-form]');
          await spot('[data-testid=approval-form]'); await sleep(2500);
          if (pr.value != null) await page.fill('[data-testid=approval-form] input[type=number]', String(pr.value));
          await page.click(pr.decision === 'reject' ? '[data-testid=reject]' : '[data-testid=approve]');
          const fin = await waitFor(async () => { const e = (await api(H, `/api/events/${ev.event_id}`)).event; return ['CLOSED', 'ESCALATED', 'REJECTED', 'VERIFY_HOLD'].includes(e.status) ? e : null; }, 150000, 'final');
          await sleep(1500);
          await page.evaluate(() => document.querySelector('[data-testid=flow]')?.scrollIntoView({ behavior: 'smooth', block: 'start' })); await sleep(900);
          await spot('.detail .cols .card:nth-child(4)');
          checks.push(`final ${fin.status}`);
        }
        break;
      }
      case 'neo4j': {
        await page.goto('http://localhost:57474/browser/'); await sleep(3500);
        const pw = await page.$('input[type=password]');
        if (pw) {
          await page.getByLabel('Connection URL').fill('localhost:57687').catch(() => {});
          await pw.fill('hydops-lecture');
          await page.getByRole('button', { name: 'Connect', exact: true }).last().click();
          await sleep(5000);
        }
        await decorate();
        await page.mouse.click(900, 90); await sleep(400);
        await page.keyboard.type(pr.cypher, { delay: 12 });
        await page.keyboard.press('Escape'); await page.keyboard.press('Meta+Enter');
        await sleep(6000); await page.mouse.click(1300, 520);
        checks.push('cypher run');
        break;
      }
      case 'console': {
        await ensureMode(SYSTEM, 'platform');
        await page.goto(`${P}/console/#${pr.tab || 'home'}`); await sleep(2000); await decorate();
        const d = pr.do;
        if (pr.tab === 'studio') {
          await page.waitForSelector('[data-testid=class-table]'); await spot('[data-testid=class-table]'); await sleep(4000);
          if (d === 'fetch' || d === 'golden') { await page.click('[data-testid=fetch]'); await page.waitForSelector('[data-testid=objects]'); await spot('[data-testid=objects]'); await sleep(3500); }
          if (d === 'golden') { await page.click('[data-testid=golden]'); await page.waitForSelector('[data-testid=golden-row]'); await spot('[data-testid=golden-row]'); checks.push('golden'); }
        } else if (pr.tab === 'agents') {
          await page.waitForSelector('[data-testid=mcp-tool]', { timeout: 30000 }); await spot('[data-testid=agent]'); await sleep(4000);
          if (d === 'call_tool') { await page.click('[data-testid=call-tool]'); await page.waitForSelector('[data-testid=tool-result]'); await spot('[data-testid=tool-result]'); checks.push('tool called'); }
        } else if (pr.tab === 'fabric') {
          await spot('[data-testid=datasource]'); await sleep(4000);
          if (d === 'sql') { await page.click('text=실행'); await sleep(1500); await spot('table.grid'); }
        } else if (pr.tab === 'process') {
          await sleep(1500); const inst = await page.$('[data-testid=instance]'); if (inst) { await inst.click(); await page.waitForSelector('[data-testid=instance-detail]'); await page.evaluate(() => document.querySelector('[data-testid=instance-detail]')?.scrollIntoView({ behavior: 'smooth' })); await spot('[data-testid=instance-detail]'); }
        } else if (pr.tab === 'apps') {
          await page.waitForSelector('[data-testid=app]'); await spot('[data-testid=app]');
        }
        break;
      }
      case 'platform_flow': {
        await ensureMode(SYSTEM, 'platform');
        await api(H, '/api/control', { reset: true, seed: 42 }); await sleep(1500);
        await api(H, '/api/sim/HYD-01/inject', { kind: pr.inject || 'cooling' });
        await page.goto(`${P}/console/#agents`); await page.waitForSelector('[data-testid=mcp-tool]', { timeout: 30000 }); await decorate();
        await spot('.watch');
        const ev = await waitFor(async () => (await api(H, '/api/events')).find(e => e.event_type === 'COOLING_ANOMALY' && e.status === 'DETECTED'), 90000, 'event');
        await page.click('[data-testid=watch-tick]'); await sleep(2000);
        await page.click('[data-testid=tab-process]'); await decorate();
        await page.waitForSelector('[data-testid=workitem]', { timeout: 180000 }); await sleep(800);
        await spot('[data-testid=workitem]'); await sleep(5000);
        if (pr.decision === 'reject') await page.selectOption('[data-testid=f-decision]', 'REJECTED');
        if (pr.value != null) await page.fill('[data-testid=f-approved_value]', String(pr.value));
        await page.fill('[data-testid=f-approver]', 'kim.operator');
        await page.click('[data-testid=complete]'); await sleep(1500);
        await page.click('[data-testid=instance]'); await page.waitForSelector('[data-testid=instance-detail]');
        await spot('[data-testid=instance-detail]');
        const inst = await waitFor(async () => (await api(P, '/process/instances')).find(x => x.event_id === ev.event_id && x.status !== 'RUNNING'), 180000, 'instance');
        await page.reload(); await decorate(); await sleep(1500); await page.click('[data-testid=instance]'); await page.waitForSelector('[data-testid=instance-detail]');
        await page.evaluate(() => document.querySelector('[data-testid=instance-detail]')?.scrollIntoView({ behavior: 'smooth' })); await spot('[data-testid=instance-detail]');
        checks.push(`instance ${inst.status} ${inst.equipment_outcome}`);
        break;
      }
      case 'app_page': {
        await ensureMode(SYSTEM, 'platform');
        await page.goto(`${P}/apps/hydops-ops/`); await page.waitForSelector('[data-testid=app-event]', { timeout: 30000 }); await decorate();
        await page.click('[data-testid=app-event]'); await page.waitForSelector('[data-testid=app-detail]'); await sleep(2500);
        await spot('[data-testid=same-event]');
        checks.push(await page.$eval('[data-testid=same-event]', e => e.innerText.replace(/\n/g, ' | ')));
        break;
      }
      case 'notebook': {
        const out = path.join(process.env.LAB_VIDEOS_DIR || path.join(LECTURE, 'video/lab_videos'), 'build/_nb');
        fs.mkdirSync(out, { recursive: true });
        execFileSync(`${SYSTEM}/.venv/bin/python`, ['-m', 'nbconvert', '--to', 'html', '--output-dir', out, path.join(LECTURE, pr.path)], { stdio: 'ignore' });
        const html = path.join(out, path.basename(pr.path).replace('.ipynb', '.html'));
        await page.goto('file://' + html); await decorate(); await sleep(1500);
        const h = await page.evaluate(() => document.body.scrollHeight);
        const steps = Math.max(6, Math.round(total / 3));
        for (let k = 1; k <= steps; k++) { await page.evaluate(y => window.scrollTo({ top: y, behavior: 'smooth' }), (h - 800) * k / steps); await sleep((total * 1000 - 3000) / steps); }
        checks.push('notebook shown');
        break;
      }
      case 'api': {
        const url = pr.url.replace('{H}', H).replace('{P}', P);
        const res = await fetch(url, pr.method === 'POST' ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pr.body || {}) } : undefined);
        const body = await res.text();
        let pretty = body; try { pretty = JSON.stringify(JSON.parse(body), null, 2); } catch { }
        const cmd = `curl -s ${pr.method === 'POST' ? `-X POST -H 'content-type: application/json' -d '${JSON.stringify(pr.body || {})}' ` : ''}${url}`;
        const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
        await page.setContent(`<!doctype html><meta charset="utf-8"><body style="margin:0;background:#0a0f1a;color:#d1d9e6;font:17px/1.5 ui-monospace,Menlo,monospace;padding:60px 36px 70px"><div style="color:#7dd3fc;margin-bottom:10px">$ ${esc(cmd)}</div><div style="color:#94a3b8">HTTP ${res.status}</div><pre id="o" style="white-space:pre-wrap;margin:8px 0 0"></pre></body>`);
        await decorate();
        const lines = pretty.split('\n').slice(0, pr.max_lines || 34);
        for (let k = 0; k < lines.length; k++) { await page.evaluate(l => { document.getElementById('o').textContent += l + '\n'; }, lines[k]); await sleep(40); }
        checks.push(`HTTP ${res.status}`);
        break;
      }
      default: throw new Error('unknown app action ' + sc.action);
    }
    await holdRest();
    return { checks, skipLead: (t0 - tStart) / 1000 + 0.4 };
  } finally {
    release();
  }
}
