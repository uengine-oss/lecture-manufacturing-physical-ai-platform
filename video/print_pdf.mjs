import { chromium } from 'playwright';
import fs from 'fs';
const dist = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage();
for (const f of fs.readdirSync(`${dist}/html`).filter(f => f.endsWith('.html'))) {
  await p.goto(`file://${dist}/html/${f}`, { waitUntil: 'load' });
  await p.pdf({ path: `${dist}/pdf/${f.replace('.html', '.pdf')}`, format: 'A4', printBackground: true, margin: { top: '16mm', bottom: '16mm', left: '12mm', right: '12mm' },
    displayHeaderFooter: true, headerTemplate: '<span></span>', footerTemplate: '<div style="font-size:9px;width:100%;text-align:center;color:#888"><span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
  console.log('pdf', f);
}
await b.close();
