#!/usr/bin/env node
/*
 * Full-page screenshot of local HTML files (or URLs) in REAL Google Chrome.
 *
 *   node shot.cjs <out-dir> <file.html|url> [more files...] [--width 1440]
 *
 * Used to look at a design-system export's own pages (Reference Sheet.html,
 * thumbnail.html, guidelines/*.html, ui_kits/*\/index.html) before mapping it.
 * Writes <out-dir>/<n>-<basename>.png and prints the paths and page errors.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const args = process.argv.slice(2);
const wi = args.indexOf('--width');
const width = wi > -1 ? Number(args.splice(wi, 2)[1]) : 1440;
const [out, ...targets] = args;
if (!out || !targets.length) { console.error('usage: shot.cjs <out-dir> <file|url>...'); process.exit(2); }
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const pg = await browser.newPage({ viewport: { width, height: 900 } });
  const res = [];
  for (const [i, t] of targets.entries()) {
    const errors = [];
    const onErr = e => errors.push(String(e.message || e));
    pg.on('pageerror', onErr);
    const url = /^https?:|^file:/.test(t) ? t : 'file://' + path.resolve(t);
    try {
      await pg.goto(url, { waitUntil: 'load', timeout: 45000 });
      await pg.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
      await pg.waitForTimeout(1500);
      const file = path.join(out, `${i + 1}-${path.basename(t).replace(/[^\w.-]+/g, '_').replace(/\.html?$/, '')}.png`);
      await pg.screenshot({ path: file, fullPage: true });
      res.push({ target: t, shot: file, errors });
    } catch (e) {
      res.push({ target: t, error: String(e.message).split('\n')[0] });
    }
    pg.off('pageerror', onErr);
  }
  await browser.close();
  console.log(JSON.stringify(res, null, 2));
})().catch(e => { console.error(e); process.exit(1); });
