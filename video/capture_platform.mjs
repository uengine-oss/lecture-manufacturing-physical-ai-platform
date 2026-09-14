import { chromium } from 'playwright';
import { execSync } from 'child_process';
const OUT = '/Users/uengine/uengine-platform/lecture/materials/screenshots';
const H = 'http://localhost:8800', P = 'http://localhost:8910';
const call = (base, u, b) => fetch(base + u, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) } : undefined).then(r => r.json());
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 180000, what = '') { const t = Date.now(); while (Date.now() - t < ms) { const v = await fn(); if (v) return v; await sleep(800); } throw new Error('timeout ' + what); }
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1480, height: 950 } });
const shot = async (n, full = true) => { await p.screenshot({ path: `${OUT}/${n}.png`, fullPage: full }); console.log('shot', n); };
const tab = async t => { await p.click(`[data-testid=tab-${t}]`); await sleep(1800); };

// 발행 전: 조회가 거부된다
await p.goto(P + '/console/#studio'); await p.waitForSelector('[data-testid=class-table]'); await p.click('[data-testid=fetch]'); await sleep(1200); await shot('S12_platform_studio_unpublished');

execSync('cd /Users/uengine/uengine-platform/lecture/system && PYTHONPATH=. .venv/bin/python scripts/bootstrap_platform.py --all', { stdio: 'inherit' });
await p.goto(P + '/console/#home'); await sleep(2000); await shot('S10_platform_home');
await tab('fabric'); await p.click('text=실행'); await sleep(1500); await shot('S11_platform_fabric');

// 사건 만들기 → Watch 한 번 실행
await call(H, '/api/control', { reset: true, seed: 42 }); await sleep(3000);
await call(H, '/api/sim/HYD-01/inject', { kind: 'cooling' });
const ev = await waitFor(async () => (await call(H, '/api/events')).find(e => e.event_type === 'COOLING_ANOMALY'), 120000, 'event');
await tab('agents'); await p.waitForSelector('[data-testid=mcp-tool]', { timeout: 30000 });
await p.click('[data-testid=call-tool]'); await p.waitForSelector('[data-testid=tool-result]');
await p.click('[data-testid=watch-tick]'); await sleep(2500); await shot('S14_platform_agents_mcp_watch');

await tab('process');
await p.waitForSelector('[data-testid=workitem]', { timeout: 180000 }); await sleep(1500);
await p.fill('[data-testid=f-approver]', 'kim.operator');
await shot('S15_platform_worklist_approval');
await p.click('[data-testid=complete]');
const inst = await waitFor(async () => (await call(P, '/process/instances')).find(i => i.event_id === ev.event_id && i.status !== 'RUNNING'), 240000, 'instance done');
await p.reload(); await sleep(2000); await p.click('[data-testid=instance]'); await p.waitForSelector('[data-testid=instance-detail]'); await sleep(1000); await shot('S16_platform_instance_closed');

await tab('studio'); await p.selectOption('select', 'Event'); await p.fill('input[placeholder=속성]', 'event_id'); await p.fill('[data-testid=obj-value]', ev.event_id);
await p.click('[data-testid=fetch]'); await p.waitForSelector('[data-testid=objects]');
await p.fill('input[placeholder=event_id]', ev.event_id); await p.click('[data-testid=golden]'); await p.waitForSelector('[data-testid=golden-row]'); await sleep(1500);
await shot('S13_platform_studio_published_golden');

await tab('apps'); await p.waitForSelector('[data-testid=app]'); await shot('S17_platform_apps');
await p.goto(P + '/apps/hydops-ops/'); await p.waitForSelector('[data-testid=app-event]', { timeout: 20000 }); await p.click('[data-testid=app-event]'); await p.waitForSelector('[data-testid=app-detail]'); await sleep(3000);
console.log('same:', await p.$eval('[data-testid=same-event]', e => e.innerText.replace(/\n/g, ' | ')));
await shot('S18_app_ops_console');
console.log(JSON.stringify({ event: ev.event_id, instance: inst.instance_id, outcome: inst.equipment_outcome }));
await b.close();
