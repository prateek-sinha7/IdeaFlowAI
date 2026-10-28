#!/usr/bin/env node
/*
 * Render a design system's components.html in REAL Google Chrome.
 *
 *   node preview_ds.cjs <od-root>/design-systems/<id> --out <shots-dir>
 *
 * Every [data-*] theme block that sets --bg is applied to <html> in turn: the
 * body background must change, and a theme-<sel>.png shot is taken.
 * Checks: no page errors, fonts named in --font-display / --font-body / --font-mono actually
 * load (document.fonts), no unresolved var() on key elements (computed colour
 * of body/buttons is not the browser default), and takes full-page shots at
 * desktop (1440) and phone (390) widths. Exit 1 on failure; prints JSON.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const dir = path.resolve(process.argv[2] || '.');
const i = process.argv.indexOf('--out');
const out = path.resolve(i > -1 ? process.argv[i + 1] : path.join(require('os').tmpdir(), 'ds-preview-' + path.basename(dir)));
if (out.startsWith(dir + path.sep)) { console.error('--out must be outside the design-system folder'); process.exit(2); }
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const pg = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  pg.on('pageerror', e => errors.push(String(e.message || e)));
  pg.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await pg.goto('file://' + path.join(dir, 'components.html'), { waitUntil: 'load' });
  await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await pg.waitForTimeout(800);
  await pg.addStyleTag({ content: '*,*::before,*::after{transition:none !important;animation:none !important}' });
  const st = await pg.evaluate(async () => {
    await document.fonts.ready;
    const root = getComputedStyle(document.documentElement);
    const v = n => root.getPropertyValue(n).trim();
    const first = s => s.split(',')[0].trim().replace(/["']/g, '');
    const want = [...new Set([first(v('--font-display')), first(v('--font-body')), first(v('--font-mono'))])].filter(f => f && !/^(system-ui|-apple-system|sans-serif|serif|monospace|ui-|helvetica|arial|georgia|verdana|menlo|monaco|consolas|sf mono)/i.test(f));
    const loaded = [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/["']/g, ''));
    const btn = document.querySelector('.btn-primary, button');
    return {
      fonts_wanted: want, fonts_missing: want.filter(f => !loaded.includes(f)),
      body_bg: getComputedStyle(document.body).backgroundColor, body_fg: getComputedStyle(document.body).color,
      button_bg: btn ? getComputedStyle(btn).backgroundColor : null,
      accent: v('--accent'), bg: v('--bg'), height: document.body.scrollHeight,
    };
  });
  await pg.screenshot({ path: path.join(out, 'desktop.png'), fullPage: true });
  // every theme block (e.g. [data-theme="dark"]) applied to <html> must re-theme the page
  const themes = await pg.evaluate(() => {
    const found = [];
    for (const s of document.styleSheets) {
      let rules; try { rules = s.cssRules; } catch (e) { continue; }
      for (const r of rules) {
        const m = r.selectorText && r.selectorText.match(/\[(data-[\w-]+)(?:=["']?([^"'\]]+)["']?)?\]/);
        if (m && r.style && r.style.getPropertyValue('--bg')) found.push({ attr: m[1], value: m[2] || '', sel: r.selectorText });
      }
    }
    return found;
  });
  const themeChecks = [];
  for (const t of themes) {
    const st2 = await pg.evaluate(t => {
      document.documentElement.setAttribute(t.attr, t.value);
      const root = getComputedStyle(document.documentElement);
      const res = { bg: root.getPropertyValue('--bg').trim(), body: getComputedStyle(document.body).backgroundColor };
      const card = document.querySelector('.card');
      res.card = card ? getComputedStyle(card).backgroundColor : null;
      return res;
    }, t);
    const safe = t.sel.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '');
    await pg.screenshot({ path: path.join(out, `theme-${safe}.png`), fullPage: true });
    await pg.evaluate(t => document.documentElement.removeAttribute(t.attr), t);
    themeChecks.push({ sel: t.sel, ...st2 });
  }
  await pg.setViewportSize({ width: 390, height: 844 });
  await pg.waitForTimeout(400);
  const overflow = await pg.evaluate(() => {
    if (document.documentElement.scrollWidth <= innerWidth + 2) return null;
    const wide = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > innerWidth + 2)
      .sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right).slice(0, 3)
      .map(e => `${e.tagName.toLowerCase()}${e.className ? '.' + String(e.className).trim().split(/\s+/).join('.') : ''} (right ${Math.round(e.getBoundingClientRect().right)}px)`);
    return { scrollWidth: document.documentElement.scrollWidth, wide };
  });
  await pg.screenshot({ path: path.join(out, 'phone.png'), fullPage: true });
  await browser.close();
  const checks = [];
  checks.push({ ok: !errors.length, msg: errors.length ? `page errors: ${errors.slice(0, 4).join(' | ')}` : 'no page errors' });
  checks.push({ ok: !st.fonts_missing.length, msg: st.fonts_missing.length ? `fonts not loaded: ${st.fonts_missing.join(', ')} (offline, or no <link>)` : `fonts loaded: ${st.fonts_wanted.join(', ') || 'system stack'}` });
  checks.push({ ok: st.body_bg !== 'rgba(0, 0, 0, 0)', msg: `body background ${st.body_bg} (--bg ${st.bg})` });
  checks.push({ ok: !!st.button_bg && st.button_bg !== 'rgba(0, 0, 0, 0)' && st.button_bg !== 'rgb(239, 239, 239)', msg: `primary button ${st.button_bg} (--accent ${st.accent})` });
  for (const t of themeChecks) {
    checks.push({ ok: t.body !== st.body_bg, msg: `theme ${t.sel}: body ${t.body} (light ${st.body_bg}), card ${t.card}` });
  }
  checks.push({ ok: !overflow, msg: overflow ? `horizontal overflow at 390px (scrollWidth ${overflow.scrollWidth}): ${overflow.wide.join(', ')}` : 'no horizontal overflow at 390px' });
  const rep = { ds: path.basename(dir), shots: out, checks, ok: checks.every(c => c.ok) };
  console.log(JSON.stringify(rep, null, 2));
  process.exit(rep.ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
