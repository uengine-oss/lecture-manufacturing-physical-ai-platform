import { chromium } from 'playwright';
const OUT = '/Users/uengine/uengine-platform/lecture/materials/screenshots';
const H = 'http://localhost:8800';
const api = (u, b) => fetch(H + u, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) } : undefined).then(r => r.json());
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 120000, what = '') { const t = Date.now(); while (Date.now() - t < ms) { const v = await fn(); if (v) return v; await sleep(700); } throw new Error('timeout ' + what); }
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1480, height: 1000 } });
const shot = async n => { await p.screenshot({ path: `${OUT}/${n}.png`, fullPage: true }); console.log('shot', n); };
async function fresh(asset = 'HYD-01') { await api('/api/control', { reset: true }); await p.goto(H); await p.waitForSelector('[data-testid=chart]'); if (asset !== 'HYD-01') await p.click(`[data-testid=asset-${asset}]`); await sleep(2500); }
async function eventOf(type, asset = 'HYD-01', status) {
  return waitFor(async () => (await api('/api/events')).find(e => e.event_type === type && e.asset_id === asset && (!status || status.includes(e.status))), 150000, type + status);
}
async function open(ev) { await p.click(`[data-testid="status-${ev.event_id}"]`); await sleep(1500); }

await fresh(); await sleep(8000); await shot('S01_dashboard_normal');

await fresh(); await api('/api/sim/HYD-01/inject', { kind: 'dropout', seconds: 25 });
let ev = await eventOf('SENSOR_FAULT', 'HYD-01', ['SENSOR_CHECK', 'HOLD_NO_EVIDENCE']); await sleep(3000); await open(ev); await shot('S02_dashboard_sensor_fault');

await fresh(); await api('/api/sim/HYD-01/inject', { kind: 'cooling' });
ev = await eventOf('COOLING_ANOMALY', 'HYD-01', ['PENDING_APPROVAL']); await open(ev); await p.waitForSelector('[data-testid=approval-form]'); await shot('S03_dashboard_pending_approval');
await p.click('[data-testid=approve]'); await eventOf('COOLING_ANOMALY', 'HYD-01', ['CLOSED']); await sleep(2500); await shot('S04_dashboard_closed');

await fresh(); await api('/api/sim/HYD-01/inject', { kind: 'severe' });
ev = await eventOf('COOLING_ANOMALY', 'HYD-01', ['PENDING_APPROVAL']); await open(ev); await p.waitForSelector('[data-testid=approval-form]'); await p.click('[data-testid=approve]');
await eventOf('COOLING_ANOMALY', 'HYD-01', ['ESCALATED']); await sleep(2500); await shot('S05_dashboard_escalated');

await fresh('HYD-03'); await api('/api/sim/HYD-03/inject', { kind: 'cooling' });
ev = await eventOf('COOLING_ANOMALY', 'HYD-03', ['HOLD_NO_EVIDENCE']); await sleep(1500); await open(ev); await shot('S06_dashboard_hold_no_evidence');

await fresh(); await api('/api/sim/HYD-01/inject', { kind: 'cooling' });
ev = await eventOf('COOLING_ANOMALY', 'HYD-01', ['PENDING_APPROVAL']); await open(ev); await p.fill('[data-testid=approval-form] input[type=number]', '0.8'); await p.click('[data-testid=reject]');
await eventOf('COOLING_ANOMALY', 'HYD-01', ['REJECTED']); await sleep(2000); await shot('S08_dashboard_rejected');

// Neo4j Browser
const n = await b.newPage({ viewport: { width: 1480, height: 950 } });
try {
  await n.goto('http://localhost:57474/browser/'); await n.waitForTimeout(3000);
  const pw = await n.$('input[type=password]');
  if (pw) {
    const url = await n.$('input[data-testid=boltaddress], input[name=url]'); if (url) await url.fill('bolt://localhost:57687');
    const user = await n.$('input[data-testid=username], input[name=username]'); if (user) await user.fill('neo4j');
    await pw.fill('hydops-lecture'); await n.keyboard.press('Enter'); await n.waitForTimeout(4000);
  }
  const editor = await n.$('.monaco-editor textarea, [data-testid=activeEditor] textarea');
  if (editor) { await editor.focus(); await n.keyboard.type("MATCH p=(s:SOP {status:'active'})-[:APPLIES_TO]->(a:Asset)-[:HAS_SENSOR]->(:Sensor) RETURN p", { delay: 5 }); await n.keyboard.press('Control+Enter'); await n.keyboard.press('Meta+Enter'); await n.waitForTimeout(6000); }
  await n.screenshot({ path: `${OUT}/S07_neo4j_browser_graph.png` }); console.log('shot S07');
} catch (e) { console.log('neo4j browser capture failed', e.message); }
await b.close();
