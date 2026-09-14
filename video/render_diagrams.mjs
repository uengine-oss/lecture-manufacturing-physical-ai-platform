import { chromium } from 'playwright';
import fs from 'fs';
const src = '/Users/uengine/uengine-platform/lecture/materials/diagrams/src';
const out = '/Users/uengine/uengine-platform/lecture/materials/diagrams';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
for (const f of fs.readdirSync(src).filter(f => f.endsWith('.html')).sort()) {
  await p.goto('file://' + src + '/' + f); await p.waitForTimeout(400);
  await (await p.$('#d')).screenshot({ path: `${out}/${f.replace('.html', '.png')}` });
  console.log('rendered', f);
}
await b.close();
