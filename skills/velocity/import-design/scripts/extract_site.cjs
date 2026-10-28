#!/usr/bin/env node
/*
 * Extract a design-system fact base from a LIVE site (or a local .html file)
 * in REAL Google Chrome.
 *
 *   node extract_site.cjs <url|file.html> --out <dir> [--pages url2,url3] [--auto-pages 2] [--wait 2500]
 *
 * Without --pages it also visits up to --auto-pages (default 2) same-origin
 * links from the header/nav (product, pricing, docs...), so components that
 * the home page lacks (forms, tables, cards) are sampled too.
 * Consent banners / cookie overlays are dismissed or hidden before sampling.
 * Page 0's data is ALSO written at the top level of site.json
 * (site.json.colors, .accents, .type, .samples, ...); every page is in .pages[].
 *
 * Writes <out>/site.json and screenshots <out>/shots/{desktop,tablet,phone}-N.png:
 *   colors      background / text / border colours ranked by painted area or
 *               text length (hex, opaque only)
 *   accents     saturated colours used on buttons and links, ranked
 *   type        font families (with usage), the font-size scale (px, ranked),
 *               weights, line-heights, letter-spacing on headings
 *   samples     computed styles of h1..h4, body text, links, primary and
 *               secondary buttons, inputs, cards, nav, footer, badges
 *   shape       border-radius, box-shadow and spacing (padding/gap) histograms
 *   root_vars   custom properties declared on :root
 *   fonts       @font-face families, Google Fonts / Typekit links
 *   breakpoints @media min/max-width values from every stylesheet (including
 *               cross-origin sheets, read from the network responses)
 *   copy        headings, buttons and nav labels (for the voice section)
 *   meta        title, description, theme-color, lang
 * Nothing is downloaded except what the page itself loads. Logos and imagery
 * are never extracted.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const argv = process.argv;
const opt = n => { const i = argv.indexOf('--' + n); return i > -1 ? argv[i + 1] : null; };
const target = argv[2];
const out = path.resolve(opt('out') || 'site-extract');
const wait = Number(opt('wait') || 2500);
const pages = [target, ...String(opt('pages') || '').split(',').filter(Boolean)];
const autoPages = opt('pages') ? 0 : Number(opt('auto-pages') || 2);
const HIDE_OVERLAYS = `#onetrust-banner-sdk,#onetrust-consent-sdk,#CybotCookiebotDialog,#usercentrics-root,.truste_overlay,.truste_box_overlay,
  [id*="cookie" i][class*="banner" i],[class*="cookie-banner" i],[class*="cookieBanner" i],[class*="consent" i][role="dialog"],
  [aria-label*="cookie" i][role="dialog"],[id*="consent" i][role="dialog"]{display:none !important}`;
if (!target) { console.error('usage: extract_site.cjs <url|file> --out <dir>'); process.exit(2); }
fs.mkdirSync(path.join(out, 'shots'), { recursive: true });
const toUrl = t => /^https?:|^file:/.test(t) ? t : 'file://' + path.resolve(t);

function inPage() {
  const toHex = c => {
    const m = String(c).match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/);
    if (!m || (m[4] !== undefined && Number(m[4]) < 0.99)) return null;
    return '#' + [m[1], m[2], m[3]].map(x => Number(x).toString(16).padStart(2, '0')).join('');
  };
  const sat = h => { const n = parseInt(h.slice(1), 16), r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b); return mx ? (mx - mn) / mx : 0; };
  const C = () => new Map();
  const bump = (m, k, w = 1) => { if (k == null || k === '') return; m.set(k, (m.get(k) || 0) + w); };
  const rank = (m, n = 15) => [...m].sort((a, b) => b[1] - a[1]).slice(0, n).map(([v, c]) => ({ v, n: Math.round(c) }));
  const bg = C(), fg = C(), border = C(), accents = C(), fam = C(), size = C(), weight = C(), radius = C(), shadow = C(), space = C();
  const els = [...document.querySelectorAll('body *')].slice(0, 8000);
  for (const e of els) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) continue;
    const r = e.getBoundingClientRect();
    if (r.width * r.height < 4) continue;
    const area = Math.min(r.width * r.height, 500000);
    bump(bg, toHex(cs.backgroundColor), area);
    const ownText = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (ownText) {
      bump(fg, toHex(cs.color), ownText.length);
      bump(fam, cs.fontFamily, ownText.length);
      bump(size, cs.fontSize, ownText.length);
      bump(weight, cs.fontWeight, ownText.length);
    }
    for (const s of ['Top', 'Right', 'Bottom', 'Left']) if (parseFloat(cs['border' + s + 'Width']) > 0 && cs['border' + s + 'Style'] !== 'none') bump(border, toHex(cs['border' + s + 'Color']));
    if (e.matches('a, button, [role=button], input[type=submit]')) {
      for (const c of [toHex(cs.backgroundColor), toHex(cs.color)]) if (c && sat(c) > 0.45) bump(accents, c, e.matches('button, [role=button]') ? 3 : 1);
    }
    if (cs.borderRadius !== '0px') bump(radius, cs.borderTopLeftRadius);
    if (cs.boxShadow !== 'none') bump(shadow, cs.boxShadow);
    for (const p of [cs.paddingTop, cs.paddingLeft, cs.gap, cs.rowGap]) if (p && p !== 'normal' && p !== '0px') bump(space, p);
  }
  const pick = (sel, n = 1) => [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }).slice(0, n);
  const props = ['color', 'backgroundColor', 'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'textTransform', 'borderRadius', 'border', 'boxShadow', 'padding', 'height'];
  const sample = e => { const cs = getComputedStyle(e); const o = { tag: e.tagName.toLowerCase(), text: (e.innerText || e.value || '').trim().slice(0, 60) }; for (const p of props) o[p] = cs[p]; return o; };
  // CTAs are often <a> elements: a link with a filled, saturated background counts as a button
  const filledLink = e => { const b = toHex(getComputedStyle(e).backgroundColor); return b && sat(b) > 0.3; };
  const buttons = [...new Set([...pick('button, a[class*=btn], a[class*=button], [role=button], input[type=submit]', 40), ...pick('a', 300).filter(filledLink)])].slice(0, 60).map(sample);
  const samples = {
    h1: pick('h1').map(sample), h2: pick('h2', 2).map(sample), h3: pick('h3', 2).map(sample), h4: pick('h4').map(sample),
    body: pick('p', 3).map(sample), link: pick('main a, article a, p a', 3).map(sample),
    buttons_filled: buttons.filter(b => toHex(b.backgroundColor) && sat(toHex(b.backgroundColor)) > 0.3).slice(0, 4),
    buttons_other: buttons.filter(b => !(toHex(b.backgroundColor) && sat(toHex(b.backgroundColor)) > 0.3)).slice(0, 4),
    input: pick('input[type=text], input[type=search], input[type=email], input:not([type]), select, textarea', 3).map(sample),
    card: pick('[class*=card], article, [class*=tile], [class*=panel]', 3).map(sample),
    nav: pick('header, nav', 2).map(sample), footer: pick('footer').map(sample),
    badge: pick('[class*=badge], [class*=chip], [class*=tag], [class*=pill]', 4).map(sample),
    table: pick('table th, table td', 4).map(sample),
  };
  const rootVars = {};
  for (const s of document.styleSheets) {
    let rules; try { rules = s.cssRules; } catch (e) { continue; }
    for (const r of rules) if (r.selectorText === ':root' || r.selectorText === 'html') for (const p of r.style) if (p.startsWith('--')) rootVars[p] = r.style.getPropertyValue(p).trim();
  }
  const faces = new Set();
  for (const f of document.fonts) faces.add(f.family.replace(/["']/g, ''));
  const links = [...document.querySelectorAll('link[href*="fonts.googleapis"], link[href*="typekit"], link[href*="fonts.com"]')].map(l => l.href);
  const txt = sel => [...new Set(pick(sel, 30).map(e => e.innerText.replace(/\s+/g, ' ').trim()).filter(t => t && t.length < 120))].slice(0, 15);
  const meta = n => (document.querySelector(`meta[name="${n}"]`) || {}).content || null;
  return {
    meta: { title: document.title, description: meta('description'), themeColor: meta('theme-color'), lang: document.documentElement.lang, url: location.href },
    colors: { background: rank(bg), text: rank(fg), border: rank(border, 8) }, accents: rank(accents, 8),
    type: { families: rank(fam, 8), sizes: rank(size, 16), weights: rank(weight, 8) },
    shape: { radius: rank(radius, 10), shadow: rank(shadow, 8), spacing: rank(space, 16) },
    samples, root_vars: rootVars, fonts: { faces: [...faces], links },
    copy: { headings: txt('h1, h2, h3'), buttons: txt('button, a[class*=btn], [role=button]'), nav: txt('nav a, header a') },
  };
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-US', extraHTTPHeaders: { 'Accept-Language': 'en-US,en;q=0.9' } });
  const pg = await ctx.newPage();
  const sheets = [];
  pg.on('response', async r => {
    try { if (r.request().resourceType() === 'stylesheet' && r.ok()) sheets.push(await r.text()); } catch (e) { /* body gone */ }
  });
  const result = { target, pages: [], errors: [] };
  for (let i = 0; i < pages.length; i++) {
    const p = pages[i];
    try {
      await pg.goto(toUrl(p), { waitUntil: 'domcontentloaded', timeout: 45000 });
      await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
      await pg.waitForTimeout(wait);
      // dismiss a cookie banner if one is obvious, so it does not dominate the histogram
      for (const t of ['Accept all', 'Accept', 'Aceptar', 'I agree', 'Agree', 'OK', 'Got it']) {
        const b = pg.getByRole('button', { name: t, exact: true });
        if (await b.count().catch(() => 0)) { await b.first().click({ timeout: 2000 }).catch(() => {}); await pg.waitForTimeout(600); break; }
      }
      await pg.addStyleTag({ content: HIDE_OVERLAYS }).catch(() => {});
      // scroll through once so lazy sections render, then back to the top
      await pg.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight && y < 20000; y += 700) { scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } scrollTo(0, 0); });
      await pg.waitForTimeout(600);
      await pg.screenshot({ path: path.join(out, 'shots', `desktop-${i + 1}.png`) });
      await pg.screenshot({ path: path.join(out, 'shots', `desktop-${i + 1}-full.png`), fullPage: true }).catch(() => {});
      const data = await pg.evaluate(inPage);
      if (i === 0 && autoPages) {
        const extra = await pg.evaluate(n => {
          const here = new URL(location.href);
          const want = /pricing|product|feature|platform|solution|docs|contact|signup|sign-up|demo|about/i;
          const links = [...document.querySelectorAll('header a[href], nav a[href]')].map(a => a.href)
            .filter(h => { try { const u = new URL(h); return u.origin === here.origin && u.pathname !== here.pathname && !u.hash; } catch (e) { return false; } });
          const ranked = [...new Set(links)].sort((a, b) => (want.test(b) ? 1 : 0) - (want.test(a) ? 1 : 0));
          return ranked.slice(0, n);
        }, autoPages).catch(() => []);
        pages.push(...extra);
        result.auto_pages = extra;
      }
      for (const [name, w, h] of [['tablet', 834, 1112], ['phone', 390, 844]]) {
        await pg.setViewportSize({ width: w, height: h });
        await pg.waitForTimeout(700);
        await pg.screenshot({ path: path.join(out, 'shots', `${name}-${i + 1}.png`) });
      }
      await pg.setViewportSize({ width: 1440, height: 900 });
      result.pages.push(data);
    } catch (e) {
      result.errors.push(`${p}: ${String(e.message).split('\n')[0]}`);
    }
  }
  // breakpoints from every stylesheet the page loaded, cross-origin included
  const inline = await pg.evaluate(() => [...document.querySelectorAll('style')].map(s => s.textContent)).catch(() => []);
  const bp = new Map();
  for (const css of [...sheets, ...inline]) {
    for (const m of css.matchAll(/@media[^{]*?\((min|max)-width\s*:\s*([\d.]+)(px|em|rem)\)/g)) {
      const px = m[3] === 'px' ? Number(m[2]) : Number(m[2]) * 16;
      const k = `${m[1]}-width:${Math.round(px)}px`;
      bp.set(k, (bp.get(k) || 0) + 1);
    }
  }
  result.breakpoints = [...bp].sort((a, b) => b[1] - a[1]).slice(0, 20).map(([v, n]) => ({ v, n }));
  result.stylesheets_read = sheets.length;
  await browser.close();
  Object.assign(result, result.pages[0] || {});
  fs.writeFileSync(path.join(out, 'site.json'), JSON.stringify(result, null, 2));
  const p0 = result.pages[0] || {};
  console.log(JSON.stringify({ out, pages: result.pages.length, errors: result.errors, title: p0.meta && p0.meta.title,
    top_bg: p0.colors && p0.colors.background.slice(0, 4), top_text: p0.colors && p0.colors.text.slice(0, 3), accents: p0.accents && p0.accents.slice(0, 4),
    families: p0.type && p0.type.families.slice(0, 4), sizes: p0.type && p0.type.sizes.slice(0, 8), breakpoints: result.breakpoints.slice(0, 6) }, null, 2));
  console.log(result.pages.length ? `OK: ${path.join(out, 'site.json')} -- ${result.pages.length} page(s), shots in ${path.join(out, 'shots')}` : 'FAILED: no page could be read');
  process.exit(result.pages.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });
