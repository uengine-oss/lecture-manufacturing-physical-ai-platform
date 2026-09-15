import { chromium } from 'playwright';
import fs from 'fs';
// 사용: node render_diagrams.mjs <src 폴더(*.html, 각 파일에 #d 요소)> <출력 폴더>
const src = process.argv[2];
const out = process.argv[3];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
for (const f of fs.readdirSync(src).filter(f => f.endsWith('.html')).sort()) {
  await p.goto('file://' + src + '/' + f); await p.waitForTimeout(400);
  await (await p.$('#d')).screenshot({ path: `${out}/${f.replace('.html', '.png')}` });
  console.log('rendered', f);
}
await b.close();
