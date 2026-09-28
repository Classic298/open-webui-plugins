// Renders every banner_*.html in this folder to a PNG at 4x via headless Chrome (CDP).
// Output: banner_<key>.html -> banner-<key>.png   (1600x400, device scale 2 x capture scale 2 = 6400x1600)
// Usage:  node render.mjs      (run `python banners.py` first to (re)generate the HTML)
// Env override: CHROME=/path/to/chrome node render.mjs
import { spawn } from 'node:child_process';
import { writeFileSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PORT = 9390;
const W = 1600, H = 400, SCALE = 2;

const files = readdirSync('.').filter(f => /^banner_.*\.html$/.test(f));
if (!files.length) { console.log('No banner_*.html found. Run: python banners.py'); process.exit(0); }

const proc = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, '--no-first-run',
  '--hide-scrollbars', '--disable-gpu', '--user-data-dir=' + (process.env.TEMP || '/tmp') + '/banner-kit-cdp', 'about:blank'],
  { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let id = 0;
const send = (ws, m, p) => new Promise(res => {
  const mid = ++id;
  const h = ev => { const x = JSON.parse(ev.data); if (x.id === mid) { ws.removeEventListener('message', h); res(x.result); } };
  ws.addEventListener('message', h); ws.send(JSON.stringify({ id: mid, method: m, params: p }));
});

let t;
for (let i = 0; i < 40; i++) { try { t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); break; } catch { await sleep(250); } }
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r, { once: true }));
await send(ws, 'Page.enable');
await send(ws, 'Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: SCALE, mobile: false });

for (const f of files) {
  const out = f.replace(/^banner_/, 'banner-').replace(/\.html$/, '.png');
  await send(ws, 'Page.navigate', { url: pathToFileURL(process.cwd() + '/' + f).href });
  await sleep(1800);
  const r = await send(ws, 'Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: W, height: H, scale: SCALE } });
  writeFileSync(out, Buffer.from(r.data, 'base64'));
  console.log('saved', out);
}
ws.close(); proc.kill();
