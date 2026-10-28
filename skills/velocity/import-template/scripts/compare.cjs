#!/usr/bin/env node
/*
 * Compare the ORIGINAL screenshots (snapshot.cjs: W/draft/shots) with the
 * template's preview screenshots (preview_check.cjs: W/preview), pair by pair.
 *
 *   node compare.cjs <original-shots-dir> <preview-shots-dir> --out <dir>
 *        [--max 12] [--mask x1,y1,x2,y2 ...]
 *
 * Pairs: <id>.png <-> <id>.png or state-<id>.png; slide-NN.png <-> slide-NN.png.
 * For each pair it writes <out>/<id>.png: original | preview | difference
 * (changed pixels in magenta), and reports the % of pixels that differ. Masked
 * boxes are ignored (e.g. a deck-stage nav pill: --mask 846,1022,1073,1058).
 * A pair over --max % is listed under "review". Originals with no preview are
 * listed under "not_compared". Prints JSON. Exit 0 always: read the composites.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const args = process.argv.slice(2);
const opt = n => { const i = args.indexOf('--' + n); return i > -1 ? args[i + 1] : null; };
const [origDir, prevDir] = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--')));
const out = path.resolve(opt('out') || 'compare');
const max = Number(opt('max') || 12);
const masks = [];
args.forEach((a, i) => { if (a === '--mask') masks.push(args[i + 1].split(',').map(Number)); });
if (!origDir || !prevDir) { console.error('usage: compare.cjs <original-shots> <preview-shots> --out <dir>'); process.exit(2); }
fs.mkdirSync(out, { recursive: true });

const originals = fs.readdirSync(origDir).filter(f => f.endsWith('.png'));
const previews = new Set(fs.readdirSync(prevDir).filter(f => f.endsWith('.png')));
const pairs = [], notCompared = [];
for (const f of originals) {
  const id = f.replace(/\.png$/, '');
  const cand = [f, `state-${f}`].find(c => previews.has(c));
  if (cand) pairs.push({ id, a: path.join(origDir, f), b: path.join(prevDir, cand) });
  else notCompared.push(id);
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const pg = await browser.newPage();
  await pg.setContent('<html><body></body></html>');
  const results = [];
  for (const p of pairs) {
    const a = 'data:image/png;base64,' + fs.readFileSync(p.a).toString('base64');
    const b = 'data:image/png;base64,' + fs.readFileSync(p.b).toString('base64');
    const r = await pg.evaluate(async ({ a, b, masks }) => {
      const load = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
      const [ia, ib] = await Promise.all([load(a), load(b)]);
      const w = ia.width, h = Math.min(ia.height, Math.round(ib.height * ia.width / ib.width)); // common height
      const ctx = (W, H) => { const c = document.createElement('canvas'); c.width = W; c.height = H; return [c, c.getContext('2d')]; };
      const [ca, xa] = ctx(w, h); xa.drawImage(ia, 0, 0);
      const [cb, xb] = ctx(w, h); xb.drawImage(ib, 0, 0, w, Math.round(ib.height * w / ib.width));
      const da = xa.getImageData(0, 0, w, h).data, db = xb.getImageData(0, 0, w, h).data;
      const [cd, xd] = ctx(w, h); xd.drawImage(ia, 0, 0); xd.fillStyle = 'rgba(255,255,255,0.7)'; xd.fillRect(0, 0, w, h);
      const dd = xd.getImageData(0, 0, w, h);
      let diff = 0, total = 0;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        if (masks.some(([x1, y1, x2, y2]) => x >= x1 && x <= x2 && y >= y1 && y <= y2)) continue;
        total++;
        const k = (y * w + x) * 4;
        if (Math.abs(da[k] - db[k]) + Math.abs(da[k + 1] - db[k + 1]) + Math.abs(da[k + 2] - db[k + 2]) > 60) {
          diff++; dd.data[k] = 255; dd.data[k + 1] = 0; dd.data[k + 2] = 200; dd.data[k + 3] = 255;
        }
      }
      xd.putImageData(dd, 0, 0);
      const [cc, xc] = ctx(w * 3 + 20, h); xc.fillStyle = '#fff'; xc.fillRect(0, 0, w * 3 + 20, h);
      xc.drawImage(ca, 0, 0); xc.drawImage(cb, w + 10, 0); xc.drawImage(cd, 2 * w + 20, 0);
      return { pct: total ? Math.round(1000 * diff / total) / 10 : 0, size: [w, h], previewSize: [ib.width, ib.height], composite: cc.toDataURL('image/png') };
    }, { a, b, masks });
    const file = path.join(out, `${p.id}.png`);
    fs.writeFileSync(file, Buffer.from(r.composite.split(',')[1], 'base64'));
    results.push({ id: p.id, diff_pct: r.pct, composite: file, size_mismatch: r.size.join('x') !== r.previewSize.join('x') ? `original ${r.size.join('x')} vs preview ${r.previewSize.join('x')} (a height change means content was added or removed)` : null });
  }
  await browser.close();
  results.sort((x, y) => y.diff_pct - x.diff_pct);
  const report = { compared: results.length, of: originals.length, max_pct: max,
    review: results.filter(r => r.diff_pct > max).map(r => r.id), not_compared: notCompared, results };
  fs.writeFileSync(path.join(out, 'compare.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch(e => { console.error(e); process.exit(1); });
