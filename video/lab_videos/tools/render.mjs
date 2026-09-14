// 차수별 실습 영상 렌더러 — node tools/render.mjs <ID> [--only 3,5] [--skip-app]
// 입력: specs/<ID>.json · build/<ID>/narration.json(gpt-6-astra) · build/<ID>/durations.json(TTS)
// 출력: build/<ID>/clips/NN.mp4 → <반>/<ID>_<제목>.mp4 + .srt + build/<ID>/report.json
import { chromium } from 'playwright';
import { spawn, execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { diffLines } from 'diff';
import { runApp } from './app_actions.mjs';

const LV = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const LECTURE = path.resolve(LV, '..', '..');
const SYSTEM = `${LECTURE}/system`;
const VENDOR = `${LV}/tools/vendor`;
const W = 1920, H = 1080, LEAD = 0.45, TAIL = 0.9, QUIZ_PAUSE = 6;

const sid = process.argv[2];
const onlyArg = process.argv.indexOf('--only');
const ONLY = onlyArg > 0 ? new Set(process.argv[onlyArg + 1].split(',').map(Number)) : null;
const SKIP_APP = process.argv.includes('--skip-app');
const spec = JSON.parse(fs.readFileSync(`${LV}/specs/${sid}.json`));
const B = `${LV}/build/${sid}`;
const NAR = JSON.parse(fs.readFileSync(`${B}/narration.json`));
const DUR = Object.fromEntries(JSON.parse(fs.readFileSync(`${B}/durations.json`)).map(d => [d.scene, d.duration]));
fs.mkdirSync(`${B}/clips`, { recursive: true });
const log = (...a) => console.log(`[${sid}]`, ...a);
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const img64 = p => `data:image/png;base64,${fs.readFileSync(`${LECTURE}/${p}`).toString('base64')}`;
const labDir = `${LECTURE}/${spec.lab}`;
const workDir = `${LECTURE}/labs_work/${path.basename(path.dirname(labDir))}/${path.basename(labDir)}`;
const relWork = path.relative(SYSTEM, workDir);
const report = { id: sid, scenes: [] };

// ---- 구간(섹션) 표시 ---------------------------------------------------------------------
const SECTIONS = ['시작', '기본 개념', '실습', '퀴즈', '해답', '요약', '다음 차수'];
let seenLab = false;
function sectionOf(sc) {
  if (sc.type === 'title') return '시작';
  if (['task', 'run', 'apply_fix'].includes(sc.type)) seenLab = true;
  if (sc.type === 'quiz') return '퀴즈';
  if (sc.type === 'answer') return '해답';
  if (sc.type === 'summary') return '요약';
  if (sc.type === 'next') return '다음 차수';
  return seenLab ? '실습' : '기본 개념';
}
const sectionMap = spec.scenes.map(sectionOf);

const CSS = `*{box-sizing:border-box}html,body{margin:0;width:${W}px;height:${H}px;overflow:hidden;font-family:Pretendard,"Apple SD Gothic Neo",sans-serif}
body{background:linear-gradient(135deg,#0b1422,#12213a);color:#eef4fb}
.top{position:absolute;left:64px;right:64px;top:34px;display:flex;align-items:center;gap:18px}
.badge{background:#1d4ed8;color:#fff;font-weight:800;border-radius:10px;padding:6px 14px;font-size:22px}
.crumb{color:#9fb3cc;font-size:22px;font-weight:600}.sp{flex:1}
.secs{display:flex;gap:6px}.secs span{font-size:16px;padding:5px 12px;border-radius:99px;background:rgba(255,255,255,.07);color:#8aa0bb}.secs span.on{background:#f59e0b;color:#1a1300;font-weight:800}
.main{position:absolute;left:64px;right:64px;top:110px;bottom:118px}
.cap{position:absolute;left:50%;bottom:34px;transform:translateX(-50%);background:rgba(4,10,20,.85);color:#fff;font-size:26px;font-weight:700;padding:12px 30px;border-radius:99px;white-space:nowrap;border:1px solid rgba(255,255,255,.12)}
h1{font-size:58px;margin:0 0 18px;letter-spacing:-.02em;line-height:1.2}h2{font-size:46px;margin:0 0 26px;letter-spacing:-.02em}
.pts{list-style:none;padding:0;margin:0}.pts li{font-size:32px;line-height:1.45;margin:0 0 18px;padding-left:44px;position:relative;color:#dbe6f3}
.pts li:before{content:'';position:absolute;left:8px;top:17px;width:14px;height:14px;border-radius:50%;background:#38bdf8}
.analogy{margin-top:26px;background:rgba(56,189,248,.12);border-left:6px solid #38bdf8;padding:18px 24px;border-radius:0 14px 14px 0;font-size:29px;color:#e0f2fe}
.note{margin-top:20px;background:rgba(245,158,11,.14);border-left:6px solid #f59e0b;padding:16px 22px;border-radius:0 14px 14px 0;font-size:27px;color:#fde68a}
.split{display:grid;grid-template-columns:1fr 1.15fr;gap:40px;height:100%;align-items:center}
.imgbox{background:#fcfcfb;border-radius:18px;padding:14px;height:100%;display:flex;align-items:center;justify-content:center}.imgbox img{max-width:100%;max-height:100%;object-fit:contain}
.full{height:calc(100% - 80px)}
.card{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:26px 30px}
.qgrid{display:flex;flex-direction:column;gap:22px}.q{font-size:31px;line-height:1.4}.q b{color:#fbbf24;margin-right:10px}.choices{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px}.choices span{font-size:25px;background:rgba(255,255,255,.08);padding:6px 16px;border-radius:10px;color:#cbd5e1}
.a{font-size:30px;line-height:1.4}.a b{color:#34d399;margin-right:10px}.why{font-size:25px;color:#b6c5d8;margin-top:6px;line-height:1.45}
.editor{background:#fff;border-radius:16px;height:100%;display:flex;flex-direction:column;overflow:hidden;color:#0f172a}
.etab{background:#e2e8f0;padding:10px 20px;font:600 21px ui-monospace,Menlo,monospace;color:#334155;display:flex;gap:16px}
.code{flex:1;overflow:hidden;font:22px/1.5 ui-monospace,Menlo,monospace;padding:14px 0}
.ln{display:flex}.ln i{width:78px;text-align:right;padding-right:20px;color:#94a3b8;font-style:normal;flex:none}.ln code{white-space:pre;padding:0}
.ln.hl{background:#fef3c7;box-shadow:inset 6px 0 0 #f59e0b}
.diff{display:grid;grid-template-columns:1fr 1fr;gap:18px;height:100%}
.dcol{background:#fff;border-radius:14px;overflow:hidden;display:flex;flex-direction:column;color:#0f172a}.dh{padding:10px 18px;font:700 21px Pretendard,sans-serif;margin-bottom:6px}.dh.b{background:#fee2e2;color:#991b1b}.dh.a{background:#dcfce7;color:#166534}
.dgrid{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:min-content;column-gap:14px;background:#fff;border-radius:14px;overflow:hidden;align-content:start;color:#0f172a}.dl{white-space:pre-wrap;word-break:break-all;font:var(--dfs,19px)/1.4 ui-monospace,Menlo,monospace;padding:1px 16px}.dl.del{background:#fee2e2}.dl.add{background:#dcfce7}.dl.pad{background:#f8fafc}.dl.gap{color:#94a3b8;text-align:center}
.steps{counter-reset:s;list-style:none;padding:0;margin:0}.steps li{counter-increment:s;font-size:31px;margin:0 0 18px;padding-left:64px;position:relative;line-height:1.4}
.steps li:before{content:counter(s);position:absolute;left:0;top:0;width:44px;height:44px;border-radius:12px;background:#1d4ed8;display:grid;place-items:center;font-weight:800;font-size:24px}
.files{margin-top:24px;display:flex;gap:12px;flex-wrap:wrap}.files span{font:22px ui-monospace,Menlo,monospace;background:rgba(255,255,255,.1);padding:6px 14px;border-radius:10px}
.term{background:#0a0f1a;border:1px solid #1f2a3d;border-radius:16px;height:100%;display:flex;flex-direction:column;overflow:hidden}
.tbar{background:#141c2b;padding:10px 18px;display:flex;gap:9px;align-items:center}.tbar i{width:14px;height:14px;border-radius:50%;display:inline-block}.tbar b{margin-left:14px;color:#94a3b8;font:500 19px ui-monospace,Menlo,monospace}
.tout{flex:1;padding:16px 22px;font:21px/1.5 ui-monospace,Menlo,monospace;color:#d1d9e6;overflow:hidden;white-space:pre-wrap;word-break:break-all}
.tout .cmd{color:#7dd3fc}.tout .fail{color:#fca5a5}.tout .pass{color:#86efac}.tout .dim{color:#64748b}
.result{position:absolute;right:40px;top:70px;font:800 30px Pretendard,sans-serif;padding:10px 24px;border-radius:12px;display:none}.result.fail{display:block;background:#dc2626;color:#fff}.result.pass{display:block;background:#16a34a;color:#fff}.result.demo{display:block;background:#475569;color:#fff}
.bigtitle{display:flex;flex-direction:column;justify-content:center;height:100%}.kick{color:#38bdf8;font-size:30px;font-weight:800;letter-spacing:.04em;margin-bottom:14px}
.meta{display:flex;gap:14px;margin:10px 0 34px;flex-wrap:wrap}.meta span{font-size:24px;background:rgba(255,255,255,.08);padding:8px 18px;border-radius:12px;color:#cbd5e1}
.nextbox{border:2px solid #38bdf8;border-radius:22px;padding:34px 40px;background:rgba(56,189,248,.08)}`;

function frame(sc, i, inner) {
  const sec = sectionMap[i - 1];
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${CSS}</style></head><body>
  <div class="top"><span class="badge">${esc(spec.class)} ${spec.session}회</span><span class="crumb">${esc(spec.title)}</span><span class="sp"></span>
  <div class="secs">${SECTIONS.map(s => `<span class="${s === sec ? 'on' : ''}">${s}</span>`).join('')}</div></div>
  <div class="main">${inner}</div>${sc.caption ? `<div class="cap">${esc(sc.caption)}</div>` : ''}</body></html>`;
}

function codeHtml(text, lang = 'python') {
  return `<link rel="stylesheet" href="file://${VENDOR}/github.min.css"><script src="file://${VENDOR}/highlight.min.js"></script><script src="file://${VENDOR}/python.min.js"></script>`;
}

function slideInner(sc) {
  switch (sc.type) {
    case 'title':
      return `<div class="bigtitle"><div class="kick">${esc(spec.class)} ${spec.session}회차 실습</div><h1 style="font-size:78px">${esc(spec.title)}</h1>
        <div class="meta"><span>${esc(spec.date)}</span><span>${esc(spec.blocks || '')}</span><span>${esc(sc.subtitle || '')}</span></div>
        <div class="card"><div style="font-size:26px;color:#93c5fd;font-weight:700;margin-bottom:14px">오늘 할 일</div><ul class="pts">${(sc.points || []).map(p => `<li>${esc(p)}</li>`).join('')}</ul></div></div>`;
    case 'concept': {
      const text = `<h2>${esc(sc.heading)}</h2><ul class="pts">${(sc.points || []).map(p => `<li>${esc(p)}</li>`).join('')}</ul>${sc.analogy ? `<div class="analogy">비유 · ${esc(sc.analogy)}</div>` : ''}${sc.note ? `<div class="note">주의 · ${esc(sc.note)}</div>` : ''}`;
      return sc.image ? `<div class="split"><div>${text}</div><div class="imgbox"><img src="${img64(sc.image)}"></div></div>` : `<div style="max-width:1500px">${text}</div>`;
    }
    case 'image':
      return `<h2>${esc(sc.heading)}</h2><div class="imgbox full"><img src="${img64(sc.image)}"></div>`;
    case 'task':
      return `<h2>${esc(sc.heading)}</h2><div class="card"><ol class="steps">${(sc.steps || []).map(s => `<li>${esc(s)}</li>`).join('')}</ol><div class="files">${(sc.files || []).map(f => `<span>${esc(f)}</span>`).join('')}</div></div>`;
    case 'quiz':
      return `<h2>퀴즈 · 잠시 멈추고 풀어 보세요</h2><div class="qgrid">${sc.questions.map((q, k) => `<div class="card q"><b>Q${k + 1}</b>${esc(q.q)}${q.choices ? `<div class="choices">${q.choices.map(c => `<span>${esc(c)}</span>`).join('')}</div>` : ''}</div>`).join('')}</div>`;
    case 'answer':
      return `<h2>해답</h2><div class="qgrid">${sc.answers.map((a, k) => `<div class="card"><div class="a"><b>A${k + 1}</b>${esc(a.a)}</div><div class="why">${esc(a.why)}</div></div>`).join('')}</div>`;
    case 'summary':
      return `<h2>오늘 정리</h2><div class="card"><ul class="pts">${sc.points.map(p => `<li>${esc(p)}</li>`).join('')}</ul></div>`;
    case 'next':
      return `<div class="bigtitle"><div class="kick">다음 차수 예고</div><div class="nextbox"><h1>${esc(spec.next.title)}</h1><div class="meta"><span>${esc(spec.class)} ${esc(spec.next.id || '')}</span><span>${esc(spec.next.date || '')}</span></div><ul class="pts">${(sc.points || []).map(p => `<li>${esc(p)}</li>`).join('')}</ul></div></div>`;
  }
  throw new Error('no slide for ' + sc.type);
}

function codeInner(sc) {
  const lines = fs.readFileSync(`${LECTURE}/${sc.file}`, 'utf8').split('\n');
  const [a, b] = sc.lines;
  const hl = new Set(sc.highlight || []);
  const rows = lines.slice(a - 1, b).map((l, k) => `<div class="ln${hl.has(a + k) ? ' hl' : ''}"><i>${a + k}</i><code class="language-python">${esc(l) || ' '}</code></div>`).join('');
  return `${codeHtml()}<h2>${esc(sc.heading)}</h2><div class="editor" style="height:calc(100% - ${sc.note ? 170 : 80}px)"><div class="etab"><span>${esc(sc.file)}</span></div><div class="code">${rows}</div></div>
  ${sc.note ? `<div class="note" style="margin-top:14px">${esc(sc.note)}</div>` : ''}
  <script>document.querySelectorAll('code').forEach(c=>{c.innerHTML=hljs.highlight(c.textContent,{language:'python'}).value})</script>`;
}

function blockOf(text, name) {
  const lines = text.split('\n');
  let st = lines.findIndex(l => l.startsWith(`def ${name}(`) || l.startsWith(`class ${name}`) || l.startsWith(`async def ${name}(`));
  if (st < 0) return text;
  while (st > 0 && lines[st - 1].startsWith('@')) st--;
  let en = lines.findIndex((l, j) => j > st && l && !/^\s/.test(l) && !/^[)\]}#]/.test(l));
  if (en < 0) en = lines.length;
  while (en > st && !lines[en - 1].trim()) en--;
  return lines.slice(st, en).join('\n');
}

function diffInner(sc, before, after) {
  const b = sc.function ? blockOf(before, sc.function) : before;
  const a = sc.function ? blockOf(after, sc.function) : after;
  const parts = diffLines(b, a);
  const rows = [];  // [{l:{t,text}, r:{t,text}}]
  const split = v => v.replace(/\n$/, '').split('\n');
  for (let k = 0; k < parts.length; k++) {
    const p = parts[k];
    if (p.removed && parts[k + 1]?.added) {
      const L = split(p.value), R = split(parts[k + 1].value);
      for (let j = 0; j < Math.max(L.length, R.length); j++) rows.push({ l: j < L.length ? { t: 'del', x: L[j] } : { t: 'pad', x: '' }, r: j < R.length ? { t: 'add', x: R[j] } : { t: 'pad', x: '' } });
      k++;
    } else if (p.removed) split(p.value).forEach(x => rows.push({ l: { t: 'del', x }, r: { t: 'pad', x: '' } }));
    else if (p.added) split(p.value).forEach(x => rows.push({ l: { t: 'pad', x: '' }, r: { t: 'add', x } }));
    else {
      const ls = split(p.value);
      const keep = sc.function ? ls : (ls.length > 5 ? [...ls.slice(0, k === 0 ? 0 : 2), null, ...ls.slice(-2)] : ls);
      keep.forEach(x => rows.push(x === null ? { l: { t: 'gap', x: '⋯' }, r: { t: 'gap', x: '⋯' } } : { l: { t: 'ctx', x }, r: { t: 'ctx', x } }));
    }
  }
  let view = rows;
  const MAX = 60;
  if (rows.length > MAX) {
    const first = Math.max(0, rows.findIndex(r => r.l.t === 'del' || r.r.t === 'add') - 3);
    view = rows.slice(first, first + MAX);
  }
  const cell = c => `<div class="dl ${c.t}">${esc(c.x) || '&nbsp;'}</div>`;
  const fontPx = Math.max(12, Math.min(19, Math.floor(19 * 30 / Math.max(view.length, 30))));  // 줄이 많으면 글자를 줄여 한 화면에 담는다
  return `<h2>${esc(sc.heading)}</h2><div class="dgrid" style="height:calc(100% - 80px);--dfs:${fontPx}px">
    <div class="dh b">고치기 전 · ${esc(sc.file)}${sc.function ? ' · ' + esc(sc.function) + '()' : ''}</div><div class="dh a">고친 뒤 · ${esc(sc.file)}${sc.function ? ' · ' + esc(sc.function) + '()' : ''}</div>
    ${view.map(r => cell(r.l) + cell(r.r)).join('')}</div>`;
}

// ---- 녹화·인코딩 ------------------------------------------------------------------------
function ff(args) { execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...args], { stdio: 'inherit' }); }
const VENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30'];
const AENC = ['-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2'];

function stillClip(png, wav, total, out, progress = false) {
  const vf = progress ? `drawbox=x=0:y=${H - 12}:w='max(2,iw*t/${total})':h=12:color=0xf59e0b:t=fill` : 'null';
  ff(['-loop', '1', '-framerate', '30', '-t', String(total), '-i', png, '-i', wav,
    '-filter_complex', `[0:v]${vf}[v];[1:a]adelay=${Math.round(LEAD * 1000)}:all=1,apad[a]`,
    '-map', '[v]', '-map', '[a]', '-t', String(total), ...VENC, ...AENC, out]);
}

function probeDur(f) { return parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', f]).toString()); }

function liveClip(webm, wav, total, out, skipLead = 0) {
  total = Math.max(total, +(probeDur(webm) - skipLead).toFixed(2));  // 실제 동작이 나레이션보다 길면 영상을 늘린다
  ff(['-ss', String(skipLead), '-i', webm, '-i', wav,
    '-filter_complex', `[0:v]scale=${W}:${H},fps=30,tpad=stop_mode=clone:stop_duration=${total}[v];[1:a]adelay=${Math.round(LEAD * 1000)}:all=1,apad[a]`,
    '-map', '[v]', '-map', '[a]', '-t', String(total), ...VENC, ...AENC, out]);
  return total;
}

const browser = await chromium.launch();

async function renderStill(html, png) {
  const p = await browser.newPage({ viewport: { width: W, height: H } });
  await p.setContent(html, { waitUntil: 'load' });
  await p.waitForTimeout(250);
  await p.screenshot({ path: png });
  await p.close();
}

async function withRecording(fn) {
  const ctx = await browser.newContext({ viewport: { width: 1536, height: 864 }, recordVideo: { dir: `${B}/rec`, size: { width: 1536, height: 864 } } });
  const page = await ctx.newPage();
  const t0 = Date.now();
  let result;
  try { result = await fn(page, t0); } finally {
    await ctx.close();
  }
  const vp = await page.video().path();
  return { webm: vp, result };
}

function normalizeCmd(cmd) {
  let c = cmd.replaceAll('{WORK}', relWork);
  if (c.includes('pytest') && !c.includes('--tb')) c += ' --tb=line';
  return c;
}

async function runScene(sc, i, total) {
  const cmd = normalizeCmd(sc.cmd);
  const tail = sc.tail || 16;
  const { webm, result } = await withRecording(async (page) => {
    await page.setContent(`<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${CSS.replaceAll(`${W}px`, '1536px').replaceAll(`${H}px`, '864px')}
      .top{left:40px;right:40px;top:22px}.badge{font-size:18px}.crumb{font-size:18px}.secs span{font-size:13px}.main{left:40px;right:40px;top:78px;bottom:86px}h2{font-size:34px;margin-bottom:14px}.tout{font-size:20px;line-height:1.45}.tbar b{font-size:16px}.cap{font-size:21px;bottom:22px}.result{top:48px;font-size:24px}</style></head><body>
      <div class="top"><span class="badge">${esc(spec.class)} ${spec.session}회</span><span class="crumb">${esc(spec.title)}</span><span class="sp"></span>
      <div class="secs">${SECTIONS.map(s => `<span class="${s === sectionMap[i - 1] ? 'on' : ''}">${s}</span>`).join('')}</div></div>
      <div class="main"><h2>${esc(sc.heading)}</h2><div class="term" style="height:calc(100% - 62px)"><div class="tbar"><i style="background:#ef4444"></i><i style="background:#f59e0b"></i><i style="background:#22c55e"></i><b>lecture/system — zsh</b></div><div class="tout" id="o"></div></div><div class="result" id="r"></div></div>
      ${sc.caption ? `<div class="cap">${esc(sc.caption)}</div>` : ''}</body></html>`);
    const o = await page.$('#o');
    const add = (html) => page.evaluate(h => { const el = document.getElementById('o'); el.insertAdjacentHTML('beforeend', h); el.scrollTop = el.scrollHeight; }, html);
    await page.waitForTimeout(700);
    // 명령을 타이핑하듯 보여 준다
    await add(`<span class="dim">~/lecture/system $ </span><span class="cmd" id="c"></span>`);
    const step = Math.max(8, Math.floor(900 / cmd.length));
    for (let k = 0; k < cmd.length; k += 3) { await page.evaluate(([s]) => { document.getElementById('c').textContent = s; }, [cmd.slice(0, k + 3)]); await page.waitForTimeout(step); }
    await add('\n');
    const started = Date.now();
    const child = spawn('/bin/zsh', ['-lc', cmd], { cwd: SYSTEM });
    let buf = '', all = '';
    const flush = async (force) => {
      const idx = buf.lastIndexOf('\n');
      if (idx < 0 && !force) return;
      const chunk = force ? buf : buf.slice(0, idx + 1); buf = force ? '' : buf.slice(idx + 1);
      const html = esc(chunk.replace(/\x1b\[[0-9;]*m/g, '')).replace(/^(.*(FAILED|Error|failed|assert).*)$/gm, '<span class="fail">$1</span>').replace(/^(.*\b(\d+ passed)\b(?!.*failed).*)$/gm, '<span class="pass">$1</span>');
      await add(html);
    };
    child.stdout.on('data', d => { buf += d; all += d; });
    child.stderr.on('data', d => { buf += d; all += d; });
    const code = await new Promise(async res => {
      let done = null; child.on('close', c => { done = c; });
      while (done === null) { await flush(false); await page.waitForTimeout(150); }
      res(done);
    });
    await flush(true);
    const got = code === 0 ? 'pass' : 'fail';
    const summary = all.trim().split('\n').slice(-1)[0] || '';
    const badge = sc.demo ? (got === 'pass' ? 'demo' : 'fail') : got;
    await page.evaluate(([g, s, demo]) => { const r = document.getElementById('r'); r.className = 'result ' + g; r.textContent = demo ? (g === 'demo' ? '실행 완료 · 출력 결과를 확인' : '실행 오류') : (g === 'pass' ? '통과 · ' : '실패 · ') + s.replace(/=+/g, '').trim(); }, [badge, summary, !!sc.demo]);
    const elapsed = (Date.now() - started) / 1000;
    const need = total * 1000 - (Date.now() - started) - 1200;
    if (need > 0) await page.waitForTimeout(need);
    return { got, code, elapsed, summary, lines: all.trim().split('\n').slice(-tail) };
  });
  if (result.got !== sc.expect) throw new Error(`scene ${i} run expected ${sc.expect} got ${result.got}: ${result.summary}`);
  return { webm, info: { cmd, expect: sc.expect, got: result.got, summary: result.summary, elapsed_s: +result.elapsed.toFixed(1) } };
}

// ---- 메인 ---------------------------------------------------------------------------------
{
  fs.rmSync(workDir, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(workDir), { recursive: true });
  fs.cpSync(labDir, workDir, { recursive: true, filter: s => !s.includes('__pycache__') && !s.includes('.pytest_cache') });
}
for (let i = 1; i <= spec.scenes.length; i++) {
  const sc = spec.scenes[i - 1];
  const wav = `${B}/audio/scene-${String(i).padStart(2, '0')}.wav`;
  const out = `${B}/clips/${String(i).padStart(2, '0')}.mp4`;
  const narr = DUR[i];
  const total = +(LEAD + narr + TAIL + (sc.type === 'quiz' ? QUIZ_PAUSE : 0)).toFixed(2);
  const entry = { scene: i, type: sc.type, section: sectionMap[i - 1], narration_s: narr, clip_s: total, caption: sc.caption };
  // apply_fix 는 부작용이 있으므로 --only 여부와 상관없이 순서대로 적용한다
  if (sc.type === 'apply_fix') {
    const before = fs.readFileSync(`${workDir}/${sc.file}`, 'utf8');
    const after = sc.function ? execFileSync(`${SYSTEM}/.venv/bin/python`, ['-c', `import sys; sys.path.insert(0, ${JSON.stringify(LV + '/tools')}); from common import fixed_text; import pathlib; print(fixed_text(pathlib.Path(sys.argv[1]).read_text(), pathlib.Path(sys.argv[2]).read_text(), sys.argv[3]), end="")`, `${workDir}/${sc.file}`, `${labDir}/solution/${sc.file}`, sc.function]).toString() : fs.readFileSync(`${labDir}/solution/${sc.file}`, 'utf8');
    if (!ONLY || ONLY.has(i)) {
      const png = `${B}/clips/${String(i).padStart(2, '0')}.png`;
      await renderStill(frame(sc, i, diffInner(sc, before, after)), png);
      stillClip(png, wav, total, out);
    }
    fs.writeFileSync(`${workDir}/${sc.file}`, after);
    entry.applied = sc.file;
    report.scenes.push(entry); log(`#${i} apply_fix ${sc.file}`);
    continue;
  }
  if (ONLY && !ONLY.has(i)) {
    if (sc.type === 'run') { /* 사이드 이펙트 없음 */ }
    continue;
  }
  if (sc.type === 'run') {
    const { webm, info } = await runScene(sc, i, total);
    entry.clip_s = liveClip(webm, wav, total, out, 0.5);
    Object.assign(entry, info);
    log(`#${i} run ${info.got} (${info.summary})`);
  } else if (sc.type === 'app') {
    if (SKIP_APP) { log(`#${i} app skipped`); continue; }
    const { webm, result } = await withRecording(page => runApp(page, sc, { total, spec, sectionMap, i, SECTIONS, LECTURE, SYSTEM }));
    entry.clip_s = liveClip(webm, wav, total, out, result?.skipLead || 0);
    entry.checks = result?.checks || [];
    log(`#${i} app ${sc.action} ${JSON.stringify(entry.checks)}`);
  } else {
    const png = `${B}/clips/${String(i).padStart(2, '0')}.png`;
    await renderStill(frame(sc, i, sc.type === 'code' ? codeInner(sc) : slideInner(sc)), png);
    stillClip(png, wav, total, out, sc.type === 'quiz');
    log(`#${i} ${sc.type}`);
  }
  report.scenes.push(entry);
}
await browser.close();
fs.rmSync(`${B}/rec`, { recursive: true, force: true });
fs.writeFileSync(`${B}/render_report.json`, JSON.stringify(report, null, 1));
log('clips done');
