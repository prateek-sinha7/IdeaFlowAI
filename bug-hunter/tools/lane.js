#!/usr/bin/env node
// Per-lane isolated Chrome for bug-hunter workers.
// Reuses ba-op's vendored Playwright runtime; does NOT touch the ba-op skill.
//   node lane.js start <lane>   -> launch real Chrome, own port + own profile
//   node lane.js run   <lane> <script.js>
//   node lane.js stop  <lane>
const path = require('path'), fs = require('fs'), os = require('os');
const { chromium } = require(path.join(os.homedir(), '.agents/skills/ba-op/node_modules/playwright'));

const STATE = path.join(__dirname, '.state');
fs.mkdirSync(STATE, { recursive: true });
const [cmd, lane, arg] = process.argv.slice(2);
if (!cmd || !lane) { console.error('usage: lane.js <start|run|stop> <lane> [script]'); process.exit(2); }
const sf = path.join(STATE, `${lane}.json`);
const PORT = 9500 + (parseInt(lane.replace(/\D/g, ''), 10) || 0);

(async () => {
  if (cmd === 'start') {
    const profile = path.join(os.tmpdir(), `bughunt-${lane}`);
    const browser = await chromium.launch({
      channel: 'chrome',              // real Google Chrome, never bundled Chromium
      headless: false,
      args: [`--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
             '--window-size=1400,1000', '--no-first-run', '--no-default-browser-check'],
    });
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded' }).catch(() => {});
    fs.writeFileSync(sf, JSON.stringify({ lane, port: PORT, profile, pid: process.pid }));
    console.log(`READY lane=${lane} port=${PORT}`);
    const bye = async () => { try { await browser.close(); } catch {} try { fs.unlinkSync(sf); } catch {} process.exit(0); };
    process.on('SIGTERM', bye); process.on('SIGINT', bye);
    await new Promise(() => {});
  }
  if (cmd === 'run') {
    if (!fs.existsSync(sf)) throw new Error(`lane ${lane} not started`);
    const { port } = JSON.parse(fs.readFileSync(sf, 'utf8'));
    const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
    const ctx = browser.contexts()[0];
    const page = ctx.pages()[0] || await ctx.newPage();
    const fn = require(path.resolve(arg));
    const out = await fn(page, { browser, context: ctx });
    if (out !== undefined) console.log(typeof out === 'string' ? out : JSON.stringify(out, null, 2));
    await browser.close();          // detaches CDP only; the lane's Chrome stays alive
  }
  if (cmd === 'stop') {
    if (fs.existsSync(sf)) { const { pid } = JSON.parse(fs.readFileSync(sf, 'utf8')); try { process.kill(pid, 'SIGTERM'); } catch {} }
    console.log(`stopped ${lane}`);
  }
})().catch(e => { console.error('ERROR:', e.message); process.exit(1); });
