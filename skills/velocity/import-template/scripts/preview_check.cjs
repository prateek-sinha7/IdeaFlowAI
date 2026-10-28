#!/usr/bin/env node
/*
 * Open a template's example.html in REAL Google Chrome and prove it works.
 *
 *   node preview_check.cjs <template-dir> [--out <shots-dir>] [--viewport 1440x900]
 *
 * prototype: every .nav-item[data-go] is clicked; the matching
 *   section.pattern must become the only visible pattern and have content.
 * deck: every slide is reached with ArrowRight; exactly one slide is visible
 *   and it is not empty.
 * prototype also: every pattern without a nav item (states, dialogs) is
 *   rendered on its own and screenshotted as state-<id>.png; style sanity
 *   (main is wide and in flow, nav items are not unstyled browser buttons,
 *   the --font-body face loaded).
 * Both: no page errors, no failed requests except fonts (offline is OK),
 *   one screenshot per screen/slide in --out (default: a temp dir, never the
 *   template folder). Exit 1 on any failure. Prints a JSON report.
 */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const dir = path.resolve(process.argv[2] || '.');
const argv = process.argv;
const opt = n => { const i = argv.indexOf('--' + n); return i > -1 ? argv[i + 1] : null; };
const out = path.resolve(opt('out') || fs.mkdtempSync(path.join(os.tmpdir(), 'tpl-preview-')));
if (out.startsWith(dir + path.sep) || out === dir) { console.error('--out must be outside the template folder'); process.exit(2); }
fs.mkdirSync(out, { recursive: true });
const file = path.join(dir, 'example.html');
// mode: --mode, else the folder's SKILL.md od.mode, else prototype (drafts have no SKILL.md yet)
const skillPath = path.join(dir, 'SKILL.md');
const skill = fs.existsSync(skillPath) ? fs.readFileSync(skillPath, 'utf8') : '';
const mode = opt('mode') || (skill.match(/^\s*mode:\s*["']?(\w+)/m) || [])[1] || 'prototype';
if (!fs.existsSync(path.join(dir, 'example.html'))) { console.error(`no example.html in ${dir}`); process.exit(2); }
const [vw, vh] = (opt('viewport') || (mode === 'deck' ? '1920x1080' : '1440x900')).split('x').map(Number);

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const pg = await browser.newPage({ viewport: { width: vw, height: vh } });
  const errors = [], failed = [];
  pg.on('pageerror', e => errors.push(String(e.message || e)));
  pg.on('console', m => { if (m.type() === 'error' && !/fonts\.(googleapis|gstatic)/.test(m.text())) errors.push('console: ' + m.text()); });
  pg.on('requestfailed', r => { if (!/fonts\.(googleapis|gstatic)/.test(r.url())) failed.push(r.url()); });
  await pg.goto('file://' + file, { waitUntil: 'load' });
  await pg.waitForTimeout(1500);
  const rep = { template: path.basename(dir), mode, shots: out, checks: [], errors, failed };
  const fail = msg => rep.checks.push({ ok: false, msg });
  const pass = msg => rep.checks.push({ ok: true, msg });

  if (mode === 'deck') {
    const n = await pg.locator('section.slide').count();
    if (n < 1) fail('no section.slide');
    for (let i = 0; i < n; i++) {
      const st = await pg.evaluate(() => {
        const vis = [...document.querySelectorAll('section.slide')].filter(s => getComputedStyle(s).display !== 'none');
        const s = vis[0];
        return { visible: vis.length, text: s ? s.innerText.trim().length : 0, kids: s ? s.querySelectorAll('*').length : 0 };
      });
      await pg.screenshot({ path: path.join(out, `slide-${String(i + 1).padStart(2, '0')}.png`) });
      if (st.visible !== 1) fail(`slide ${i + 1}: ${st.visible} slides visible`);
      else if (!st.text && st.kids < 3) fail(`slide ${i + 1}: empty`);
      else pass(`slide ${i + 1} ok`);
      await pg.keyboard.press('ArrowRight');
      await pg.waitForTimeout(250);
    }
  } else {
    const ids = await pg.$$eval('.nav-item[data-go]', els => els.map(e => e.getAttribute('data-go')));
    const thin = /^\s*shape:\s*["']?thin/m.test(skill);
    if (thin) {
      const navs = await pg.locator('.nav-item').count();
      if (navs < 2) fail(`thin template: only ${navs} .nav-item`);
      if (ids.length < 1) fail('thin template: no .nav-item[data-go] for the finished screen');
    } else if (ids.length < 2) fail(`only ${ids.length} .nav-item[data-go]`);
    for (const id of ids) {
      await pg.keyboard.press('Escape');  // close an overlay left open by the previous item
      await pg.locator(`.nav-item[data-go="${id}"]`).first().click();
      await pg.waitForTimeout(250);
      const st = await pg.evaluate(id => {
        const vis = [...document.querySelectorAll('section.pattern')].filter(s => !s.hidden && getComputedStyle(s).display !== 'none');
        const want = document.querySelector(`section.pattern[data-pattern="${id}"]`);
        const r = want ? want.getBoundingClientRect() : { height: 0 };
        const under = want && want.getAttribute('data-under');
        const active = document.querySelector(`.nav-item[data-go="${id}"]`).classList.contains('is-active') || !!(under && document.querySelector(`.nav-item[data-go="${under}"].is-active`));
        return { visible: vis.map(v => v.getAttribute('data-pattern')), height: r.height, text: want ? want.innerText.trim().length : 0, active };
      }, id);
      await pg.screenshot({ path: path.join(out, `${id}.png`), fullPage: true });
      const okVisible = st.visible.includes(id) && st.visible.length <= 2;
      if (!okVisible) fail(`${id}: visible patterns ${JSON.stringify(st.visible)}`);
      else if (st.height < 40 || st.text < 10) fail(`${id}: pattern looks empty (h=${st.height}, text=${st.text})`);
      else if (!st.active) fail(`${id}: nav item not marked is-active`);
      else pass(`${id} ok (h=${Math.round(st.height)})`);
    }
    // every pattern, including states without a nav item, is rendered on its own
    const all = await pg.$$eval('section.pattern', els => els.map(e => e.getAttribute('data-pattern')));
    for (const id of all.filter(h => !ids.includes(h))) {
      const st = await pg.evaluate(id => {
        if (window.__show) window.__show(id);  // the template's own runtime: overlays show over their host screen
        else document.querySelectorAll('section.pattern').forEach(s => { s.hidden = s.getAttribute('data-pattern') !== id; });
        const s = document.querySelector(`section.pattern[data-pattern="${id}"]`);
        const r = s.getBoundingClientRect();
        return { h: r.height, text: s.innerText.trim().length, kids: s.querySelectorAll('*').length };
      }, id);
      const isOverlay = await pg.evaluate(id => !!document.querySelector(`section.pattern-overlay[data-pattern="${id}"]`), id);
      await pg.screenshot({ path: path.join(out, `state-${id}.png`), fullPage: !isOverlay });
      if (st.text < 10 && st.kids < 5) fail(`state ${id}: renders empty`);
      else pass(`state ${id} rendered (h=${Math.round(st.h)})`);
    }
    // style sanity: the frame must look styled, not like browser defaults
    const sane = await pg.evaluate(() => {
      const main = document.querySelector('main');
      const item = document.querySelector('.nav-item');
      const ics = item && getComputedStyle(item);
      const root = getComputedStyle(document.documentElement);
      const fam = root.getPropertyValue('--font-body').split(',')[0].trim().replace(/["']/g, '');
      const loaded = [...document.fonts].some(f => f.status === 'loaded' && f.family.replace(/["']/g, '') === fam);
      return {
        mainWidth: main ? main.getBoundingClientRect().width / innerWidth : 0,
        mainPos: main ? getComputedStyle(main).position : null,
        defaultButton: ics ? (ics.backgroundColor === 'rgb(239, 239, 239)' || /outset/.test(ics.borderTopStyle)) : false,
        fam, loaded, system: /^(system-ui|-apple-system|sans-serif|serif|ui-|helvetica|arial)/i.test(fam) || !fam,
        bodyBg: getComputedStyle(document.body).backgroundColor,
      };
    });
    if (sane.mainWidth < 0.4) fail(`<main> is only ${Math.round(sane.mainWidth * 100)}% of the viewport width -- frame CSS is probably lost`);
    if (/absolute|fixed/.test(sane.mainPos || '')) fail(`<main> is position:${sane.mainPos}`);
    if (sane.defaultButton) fail('nav items render as default browser buttons -- their CSS is missing');
    if (!sane.system && !sane.loaded) fail(`--font-body "${sane.fam}" did not load (offline, or no @import)`);
    else pass(`body font ${sane.fam || 'system'} ${sane.system ? '(system stack)' : 'loaded'}`);
  }
  if (errors.length) fail(`page errors: ${errors.slice(0, 5).join(' | ')}`);
  if (failed.length) fail(`failed requests: ${failed.slice(0, 5).join(' | ')}`);
  await browser.close();
  rep.ok = rep.checks.every(c => c.ok);
  console.log(JSON.stringify(rep, null, 2));
  process.exit(rep.ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
