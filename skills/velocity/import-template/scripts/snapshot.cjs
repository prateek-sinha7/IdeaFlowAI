#!/usr/bin/env node
/*
 * Render an HTML prototype or deck in REAL Google Chrome and write a static,
 * pipeline-ready draft `example.html` for a VelocityAI template.
 *
 *   node snapshot.cjs --entry <file.html> --out <dir> --kind prototype|deck
 *        [--config cfg.json] [--viewport 1440x900] [--prefix tp] [--title "Name"]
 *        [--expect-screens N] [--split h2] [--keep]
 *
 * prototype:
 *   1. Opens the page (file://) and waits for it to settle.
 *   2. Finds the content area (<main> or config.content) and the nav items
 *      (buttons/links in the first <nav>/<aside>, or config.nav).
 *   3. Clicks every nav item and captures the content area as one screen.
 *      Then runs config.states (role switches, dialogs, wizard steps, variants).
 *   4. Turns every inline style="" into a shared class (<prefix>-<n>). The
 *      class map lives in Node, so page reloads (`reset`) never renumber it.
 *      Drops runtime attributes/wrappers (data-dc-*, data-screen-label,
 *      sc-host, sc-interp, #dc-root, x-dc).
 *   5. Collects every CSS rule the page uses, including rules a runtime
 *      inserted with insertRule. Dedupes them (keep-last), drops runtime-only
 *      rules, prunes rules for classes the markup never uses, and bridges the
 *      role colours/fonts (and success/warn/danger/info from the source
 *      tokens) to :root variables.
 *   6. Writes out/example.html (frame: .nav-item[data-go] before <main>, one
 *      section.pattern[data-pattern] per screen/state), out/snapshot-report.json
 *      and out/shots/<id>.png (screenshots of the ORIGINAL for comparison).
 *   With no nav but config.states, or with --split h2 (a document), a frame
 *   (brand bar + nav + main) is generated around the captured sections.
 *   If nothing is captured it exits 3 and writes no example.html.
 *
 * deck: screenshots every ORIGINAL slide (out/shots/slide-NN.png), then
 *   captures each slide (<deck-stage> children, section.slide, .slide or
 *   [data-om-slide-id]) into a 1920x1080 `div.deck > section.slide` frame with
 *   an inline keyboard/hash navigation script. No external assets.
 *
 * --keep: the input is already a static page; copy it and inline local
 *   <link> stylesheets and <script src> files. No capture.
 *
 * Config (all optional). `content` and `nav` are CSS selectors. Step `click`,
 * `type[0]` and `hover` accept Playwright selectors (css, text=Label, role=...).
 *   { "content": "main", "nav": "nav button", "wait": 600, "settle": 2500,
 *     "skipNav": ["Sign out"],
 *     "states": [ { "id": "approval-dialog", "purpose": "Confirm a batch",
 *                   "reset": false,           // true: reload the page first
 *                   "steps": [ {"click": "text=Approve batch"}, {"wait": 500},
 *                              {"type": ["#q", "ABC"]}, {"press": "Enter"} ],
 *                   "capture": "[role=dialog]",   // default: the content area
 *                   "overlay": true,      // dialog/drawer: preview it over a scrim
 *                   "nav": true, "label": "Supervisor", "icon": "monitoring" } ] }
 *   States run in order AFTER the nav pass. Without `reset` a state starts from
 *   wherever the previous one left the page.
 *   `nav: true` adds a nav item for the state (role-only screens).
 *   "navTo": { "AI assistant": "ai-drawer" } makes that nav item open the named
 *   state instead of capturing its own (duplicate) screen.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const css = require('./css_tools.cjs');

const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1) return dflt;
  const v = process.argv[i + 1];
  return v === undefined || v.startsWith('--') ? true : v;
}
const entry = arg('entry');
const out = arg('out');
const kind = arg('kind', 'prototype');
const cfg = arg('config') ? JSON.parse(fs.readFileSync(arg('config'), 'utf8')) : {};
const [vw, vh] = String(arg('viewport', kind === 'deck' ? '1920x1080' : '1440x900')).split('x').map(Number);
const prefix = String(arg('prefix', 'tp')).replace(/[^a-z0-9]/gi, '').toLowerCase() || 'tp';
const title = arg('title', '');
const expectScreens = Number(arg('expect-screens', 0)) || 0;
const split = arg('split', null);
if (!entry || !out) {
  console.error('usage: snapshot.cjs --entry <html> --out <dir> --kind prototype|deck');
  process.exit(2);
}
fs.mkdirSync(path.join(out, 'shots'), { recursive: true });
try { fs.unlinkSync(path.join(out, 'example.html')); } catch (e) { /* none yet */ }

const slug = s => String(s).toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
  .replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  .replace(/^\d+-(?=[a-z])/, '')                 // "01 Disruption board" -> disruption-board
  .replace(/^(.{40}[^-]*)-.*$/, (m, a) => a.length > 48 ? a.slice(0, 40).replace(/-[^-]*$/, '') : a) // cut long ids at a word boundary
  || 'screen';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const STATE_CLASSES = /^(is-|has-)|^(active|open|show|shown|hidden|selected|current|disabled|expanded|collapsed|checked|visible|on|off)$/;

/* ---------------------------------------------------------------- keep mode */
function keepMode() {
  let html = fs.readFileSync(entry, 'utf8');
  const dir = path.dirname(entry);
  const inlined = [], missing = [];
  html = html.replace(/<link\b[^>]*rel=["']?stylesheet["']?[^>]*>/gi, tag => {
    const m = tag.match(/href=["']([^"']+)["']/i);
    if (!m || /^https?:|^data:/i.test(m[1])) return tag;
    const p = path.resolve(dir, m[1]);
    if (!fs.existsSync(p)) { missing.push(m[1]); return tag; }
    inlined.push(m[1]);
    return `<style>/* inlined ${m[1]} */\n${fs.readFileSync(p, 'utf8')}\n</style>`;
  });
  html = html.replace(/<script\b([^>]*)\bsrc=["']([^"']+)["']([^>]*)><\/script>/gi, (tag, a, src, b) => {
    if (/^https?:|^data:/i.test(src)) return tag;
    const p = path.resolve(dir, src);
    if (!fs.existsSync(p)) { missing.push(src); return tag; }
    inlined.push(src);
    return `<script${a}${b}>/* inlined ${src} */\n${fs.readFileSync(p, 'utf8').replace(/<\/script/gi, '<\\/script')}\n</script>`;
  });
  fs.writeFileSync(path.join(out, 'example.html'), html);
  const report = { mode: 'keep', entry, inlined, missing, chars: html.length,
    external_urls: [...new Set((html.match(/https?:\/\/[^"')\s>]+/g) || []).filter(u => !/w3\.org/.test(u)))] };
  fs.writeFileSync(path.join(out, 'snapshot-report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

/* --------------------------------------------------------- in-page helpers */
// Installed into the page after every load; everything below runs in the browser.
function installHelpers({ prefix, entries }) {
  const SKIP_ATTR = /^(data-dc|data-reactroot|data-react|data-sc-|data-om-|data-testid$|data-screen-label$|data-snap-)/;
  window.__styleMap = new Map(entries);
  window.__cls = function (decl) {
    // Claude Design writes `all: unset` as ~300 `x: unset` longhands. Collapse
    // them back to one `all: unset` (dropping them would bring back the
    // browser's default button borders and centred text).
    const parts = decl.split(';').map(d => d.trim()).filter(Boolean);
    const unset = parts.filter(d => /:\s*unset\s*(!important)?$/i.test(d) && !/^all\s*:/i.test(d));
    const rest = parts.filter(d => !unset.includes(d));
    if (unset.length > 20 && !rest.some(d => /^all\s*:/i.test(d))) rest.unshift('all: unset');
    const norm = rest.join('; ');
    if (!norm) return null;
    let c = window.__styleMap.get(norm);
    if (!c) { c = `${prefix}-${window.__styleMap.size.toString(36)}`; window.__styleMap.set(norm, c); }
    return c;
  };
  window.__label = function (el) {
    const l = el.getAttribute('data-screen-label') || el.getAttribute('data-label') || el.getAttribute('data-om-slide-label');
    if (l) return l.trim();
    const h = el.querySelector('h1, h2, h3');
    if (!h) return '';
    const c = h.cloneNode(true);
    c.querySelectorAll('br').forEach(b => b.replaceWith(' '));
    return c.textContent.replace(/\s+/g, ' ').trim();
  };
  // Clean a live element's clone: inline styles -> classes, drop runtime attrs and wrappers.
  window.__clean = function (el, keepAttr) {
    // live form state (checked, typed value, selected option) is not in the DOM attributes: copy it over
    for (const i of el.querySelectorAll('input, textarea, select')) {
      if (i.type === 'checkbox' || i.type === 'radio') { if (i.checked) i.setAttribute('checked', ''); else i.removeAttribute('checked'); }
      else if (i.tagName === 'SELECT') { [...i.options].forEach(o => { if (o.selected) o.setAttribute('selected', ''); else o.removeAttribute('selected'); }); }
      else if (i.tagName === 'TEXTAREA') i.textContent = i.value;
      else if (i.value != null && i.type !== 'password') i.setAttribute('value', i.value);
    }
    const root = el.cloneNode(true);
    const all = [root, ...root.querySelectorAll('*')];
    for (const n of all) {
      if (n.tagName === 'SCRIPT' || n.tagName === 'TEMPLATE') { n.remove(); continue; }
      for (const a of [...n.attributes]) {
        if ((SKIP_ATTR.test(a.name) && !(keepAttr && keepAttr.test(a.name))) || /^on/i.test(a.name)) n.removeAttribute(a.name);
      }
      const st = n.getAttribute && n.getAttribute('style');
      if (st != null) {
        n.removeAttribute('style');
        const c = window.__cls(st);
        if (c) n.classList.add(c);
      }
    }
    // unwrap runtime wrappers (React host / interpolation spans / control-flow tags)
    for (const h of [...root.querySelectorAll('.sc-host, .sc-host-x, span.sc-interp, sc-if, sc-for, sc-else, x-import, x-dc, #dc-root')]) {
      h.replaceWith(...h.childNodes);
    }
    for (const n of [root, ...root.querySelectorAll('[class]')]) {
      if (!n.classList) continue;
      for (const c of [...n.classList]) if (/^sc-(host|interp|shine)/.test(c)) n.classList.remove(c);
      if (n.getAttribute('class') === '') n.removeAttribute('class');
    }
    return root;
  };
  // Raw stylesheet text is preferred over cssRules: Chrome serialises a rule
  // whose shorthand uses var() (`font: 600 18px var(--x)`) with EMPTY longhands.
  // Rules a runtime added with insertRule are NOT in the raw text, so they are
  // appended from cssRules.
  window.__collectCss = async function () {
    const seen = new Set(), rules = [], fontFaces = [], imports = new Set();
    const sheets = [...document.styleSheets, ...(document.adoptedStyleSheets || [])];
    for (const s of sheets) {
      let list;
      try { list = [...s.cssRules]; } catch (e) { continue; }
      for (const r of list) {
        if (r.type === CSSRule.FONT_FACE_RULE) {
          fontFaces.push({ family: r.style.getPropertyValue('font-family').replace(/["']/g, '').trim(),
            weight: r.style.getPropertyValue('font-weight'), style: r.style.getPropertyValue('font-style'),
            embedded: /url\(\s*["']?data:/.test(r.cssText) });
        }
      }
      let text = null;
      const owner = s.ownerNode;
      if (owner && owner.tagName === 'STYLE') text = owner.textContent;
      else if (owner && owner.tagName === 'LINK' && owner.href) {
        try { text = await (await fetch(owner.href)).text(); } catch (e) { text = null; }
      }
      const ser = r => r.type === CSSRule.IMPORT_RULE ? `/* @import ${r.href} */` : r.cssText;
      if (text == null || !text.trim()) {
        text = list.filter(r => r.type !== CSSRule.FONT_FACE_RULE).map(ser).join('\n');
      } else {
        const rawCount = (text.replace(/\/\*[\s\S]*?\*\//g, '').match(/\{/g) || []).length;
        if (list.length > rawCount + 2) {
          // runtime-inserted rules: append those whose selector the raw text lacks
          const extra = list.filter(r => r.type !== CSSRule.FONT_FACE_RULE && !(r.selectorText && text.includes(r.selectorText)));
          text += '\n/* rules inserted at runtime */\n' + extra.map(ser).join('\n');
        }
      }
      text = text.replace(/@font-face\s*\{[^}]*\}/g, '')
        .replace(/@import\s+(?:url\()?\s*["']?([^"')\s;]+)["']?\s*\)?[^;]*;/g, (m, u) => {
          if (/^https?:\/\/fonts\.googleapis\.com\//.test(u)) imports.add(u);
          return '';
        })
        .replace(/\/\*#\s*sourceMappingURL=[^*]*\*\//g, '').trim();
      if (text && !seen.has(text)) { seen.add(text); rules.push(text); }
    }
    for (const l of document.querySelectorAll('link[rel=stylesheet][href*="fonts.googleapis.com"]')) imports.add(l.href);
    return { css: rules, fontFaces, imports: [...imports] };
  };
  const toHex = c => {
    const m = String(c).match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/);
    if (!m) return null;
    if (m[4] !== undefined && Number(m[4]) < 0.99) return null;
    return '#' + [m[1], m[2], m[3]].map(x => Number(x).toString(16).padStart(2, '0')).join('');
  };
  window.__roles = function (scopeSel, pageBgSel) {
    const scope = (scopeSel && document.querySelector(scopeSel)) || document.body;
    const count = new Map();
    const bump = (k, v, w = 1) => { if (!v) return; const key = k + '|' + v; count.set(key, (count.get(key) || 0) + w); };
    const els = [...scope.querySelectorAll('*')].slice(0, 6000);
    for (const e of els) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = e.getBoundingClientRect();
      const area = Math.min(r.width * r.height, 400000);
      if (area < 1) continue;
      const bg = toHex(cs.backgroundColor);
      if (bg) bump('bg', bg, area);
      if ([...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) bump('fg', toHex(cs.color), e.textContent.length);
      for (const side of ['Top', 'Bottom', 'Left', 'Right']) {
        if (parseFloat(cs['border' + side + 'Width']) > 0 && cs['border' + side + 'Style'] !== 'none') bump('border', toHex(cs['border' + side + 'Color']), 1);
      }
      if (bg && e.matches('button, a.btn, [role=button], .btn, [class*=primary]')) bump('btn', bg, 1);
    }
    const top = k => [...count].filter(([key]) => key.startsWith(k + '|')).sort((a, b) => b[1] - a[1]).map(([key, n]) => ({ v: key.split('|')[1], n }));
    const sat = h => { const n = parseInt(h.slice(1), 16), r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b); return mx ? (mx - mn) / mx : 0; };
    const lum = h => { const n = parseInt(h.slice(1), 16); return (0.2126 * (n >> 16 & 255) + 0.7152 * (n >> 8 & 255) + 0.0722 * (n & 255)) / 255; };
    const pageEl = (pageBgSel && document.querySelector(pageBgSel)) || scope;
    const scopeBg = toHex(getComputedStyle(pageEl).backgroundColor) || toHex(getComputedStyle(document.body).backgroundColor)
      || toHex(getComputedStyle(document.documentElement).backgroundColor) || '#ffffff'; // transparent page = white canvas
    const bgs = top('bg'), fgs = top('fg'), borders = top('border'), btns = top('btn');
    const page = scopeBg || (bgs[0] && bgs[0].v) || '#ffffff';
    const surface = (bgs.find(x => x.v !== page && Math.abs(lum(x.v) - lum(page)) < 0.25 && sat(x.v) < 0.3) || {}).v || page;
    // fg: among the text colours carrying >= 15% of the text, the one with the most contrast to the page
    const totalText = fgs.reduce((a, x) => a + x.n, 0) || 1;
    const major = fgs.filter(x => x.n >= 0.15 * totalText);
    const fg = (major.sort((a, b) => Math.abs(lum(b.v) - lum(page)) - Math.abs(lum(a.v) - lum(page)))[0] || fgs[0] || {}).v
      || toHex(getComputedStyle(document.body).color) || '#111111';
    // muted: a low-saturation text colour between fg and the page in lightness
    const between = x => (lum(x.v) - lum(fg)) * (lum(page) - lum(fg)) > 0 && Math.abs(lum(x.v) - lum(page)) > 0.15;
    const muted = (fgs.find(x => x.v !== fg && sat(x.v) < 0.25 && between(x)) || {}).v || null;
    const border = (borders.find(x => sat(x.v) < 0.2 && x.v !== fg) || {}).v || null;
    let accent = (btns.find(x => sat(x.v) > 0.35) || bgs.find(x => sat(x.v) > 0.45) || {}).v || null;
    if (!accent) { // documents: the heading colour or its rule colour
      for (const h of scope.querySelectorAll('h1, h2, h3')) {
        const cs = getComputedStyle(h);
        for (const c of [cs.color, cs.borderBottomColor, cs.borderLeftColor]) { const x = toHex(c); if (x && sat(x) > 0.35) { accent = x; break; } }
        if (accent) break;
      }
    }
    let accentOn = null;
    if (accent) {
      const b = [...document.querySelectorAll('button, [role=button], a')].find(e => toHex(getComputedStyle(e).backgroundColor) === accent);
      accentOn = b ? toHex(getComputedStyle(b).color) : (lum(accent) > 0.55 ? '#111111' : '#ffffff');
    }
    const fam = e => e ? getComputedStyle(e).fontFamily : null;
    const mono = [...scope.querySelectorAll('code, kbd, pre, td, span, div')].map(fam).find(f => f && /mono|courier|consolas/i.test(f)) || null;
    // semantic colours declared by the source's own tokens
    const semantic = {};
    const SEM = [[/success|positive|ok\b/, '--success'], [/warn/, '--warn'], [/critical|danger|error|negative/, '--danger'], [/info\b|information/, '--info']];
    for (const s of document.styleSheets) {
      let rules; try { rules = s.cssRules; } catch (e) { continue; }
      for (const r of rules) {
        if (r.selectorText !== ':root' || !r.style) continue;
        for (const p of r.style) {
          const v = r.style.getPropertyValue(p).trim();
          if (!/^#[0-9a-f]{3,8}$/i.test(v) || /bg|tint|fill|soft|light|hover|on-|surface/.test(p)) continue;
          for (const [re, role] of SEM) if (re.test(p) && !semantic[role]) semantic[role] = v.toLowerCase().length === 4 ? '#' + [...v.slice(1).toLowerCase()].map(c => c + c).join('') : v.toLowerCase();
        }
      }
    }
    return {
      colors: { '--bg': page, '--surface': surface, '--fg': fg, '--muted': muted, '--border': border, '--accent': accent, '--accent-on': accentOn, ...semantic },
      fonts: { '--font-display': fam(scope.querySelector('h1, h2, h3, [class*=title]')) || fam(scope), '--font-body': fam(scope) || getComputedStyle(document.body).fontFamily, '--font-mono': mono },
      ranked: { bg: bgs.slice(0, 8), fg: fgs.slice(0, 8), border: borders.slice(0, 5), btn: btns.slice(0, 5) },
      lang: document.documentElement.lang || '',
    };
  };
}

/* ---------------------------------------------------------- page actions */
async function runSteps(pg, steps) {
  for (const s of steps || []) {
    if (s.click) await pg.locator(s.click).first().click({ timeout: 5000 });
    else if (s.type) await pg.locator(s.type[0]).first().fill(s.type[1]);
    else if (s.press) await pg.keyboard.press(s.press);
    else if (s.hover) await pg.locator(s.hover).first().hover();
    await pg.waitForTimeout(s.wait || cfg.wait || 500);
  }
}

const hexToRgb = h => { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };

function rewriteColors(text, roles) {
  // Literal role colours (hex or rgb) outside :root become var(--role).
  const pairs = Object.entries(roles.colors).filter(([, v]) => v);
  const used = {};
  const outText = css.map(text, it => {
    if (it.kind === 'rule' && /^:root\b/.test(it.head)) return undefined;
    if (it.kind === 'block-at' && /^@(keyframes|font-face)/i.test(it.head)) return undefined;
    if (it.kind !== 'rule') return undefined;
    let body = it.body;
    for (const [name, hex] of pairs) {
      const [r, g, b] = hexToRgb(hex);
      const short = /^#(.)\1(.)\2(.)\3$/i.test(hex) ? '#' + hex[1] + hex[3] + hex[5] : null;
      const pats = [new RegExp(hex + '(?![0-9a-f])', 'gi'), new RegExp(`rgb\\(\\s*${r}\\s*,\\s*${g}\\s*,\\s*${b}\\s*\\)`, 'g')];
      if (short) pats.push(new RegExp(short + '(?![0-9a-f])', 'gi'));
      for (const p of pats) body = body.replace(p, () => { used[name] = (used[name] || 0) + 1; return `var(${name})`; });
    }
    return `${it.head}{${body}}`;
  });
  return { css: outText, used };
}

// A source :root custom property whose value is a role colour becomes var(--role).
function bridgeRoot(text, roles) {
  const byHex = {};
  for (const [k, v] of Object.entries(roles.colors)) if (v) (byHex[v] = byHex[v] || []).push(k);
  const HINTS = [[/on-|-on\b|inverse/, '--accent-on'], [/line|border|rule|divider/, '--border'],
    [/muted|subtle|secondary|meta/, '--muted'], [/success|positive/, '--success'], [/warn/, '--warn'],
    [/critical|danger|error/, '--danger'], [/info/, '--info'], [/ink|text|fg|foreground/, '--fg'],
    [/canvas|page|app-bg|background|-bg\b/, '--bg'], [/surface|card|panel|white/, '--surface'],
    [/brand|primary|accent|action|red|blue/, '--accent']];
  const pick = (name, list) => {
    for (const [re, role] of HINTS) if (re.test(name) && list.includes(role)) return role;
    return null; // no name evidence: leave the literal (coincidental equal hex)
  };
  const bridged = [], unbridged = [];
  const outText = css.map(text, it => {
    if (it.kind !== 'rule' || it.head !== ':root') return undefined;
    const nb = it.body.replace(/(--[\w-]+)\s*:\s*(#[0-9a-f]{3,8}|rgb\([^)]*\))\s*;?/gi, (d, name, val) => {
      let hex = val.toLowerCase();
      const m = hex.match(/rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*\)/);
      if (m) hex = '#' + [m[1], m[2], m[3]].map(x => Number(x).toString(16).padStart(2, '0')).join('');
      if (/^#(.)(.)(.)$/.test(hex)) hex = '#' + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
      if (!byHex[hex]) return d;
      const role = pick(name, byHex[hex]);
      if (role && role !== name) { bridged.push(`${name} -> var(${role})`); return `${name}: var(${role});`; }
      if (!role) unbridged.push(`${name} (${hex} equals ${byHex[hex].join('/')}, name gives no role)`);
      return d;
    });
    return `:root{${nb}}`;
  });
  return { css: outText, bridged: [...new Set(bridged)], unbridged: [...new Set(unbridged)] };
}

const GENERIC = /^(serif|sans-serif|monospace|system-ui|ui-[a-z-]+|-apple-system|blinkmacsystemfont|segoe ui|helvetica|helvetica neue|arial|verdana|geneva|tahoma|georgia|times|times new roman|menlo|monaco|consolas|courier|courier new|inherit|initial|sf mono|sf pro.*|apple color emoji|segoe ui emoji)$/i;
const fontImports = [];
function googleFontsImport(families) {
  // Keep the source's own Google Fonts imports; generate one only for families
  // the source embedded (data: URL @font-face) and does not import.
  const kept = [...new Set(fontImports)];
  const covered = kept.join(' ').replace(/\+/g, ' ').toLowerCase();
  const fams = [...new Set(families)].filter(f => f && !GENERIC.test(f) && !covered.includes('family=' + f.toLowerCase()));
  const keptCss = kept.map(u => `@import url('${u}');`).join('\n');
  if (!fams.length) return keptCss;
  const q = fams.map(f => /material symbols/i.test(f)
    ? 'family=' + f.replace(/ /g, '+') + ':opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200'
    : 'family=' + f.replace(/ /g, '+') + ':wght@400;500;600;700').join('&');
  return (keptCss ? keptCss + '\n' : '') + `@import url('https://fonts.googleapis.com/css2?${q}&display=swap');`;
}

function rootBlock(roles, families) {
  const lines = [];
  for (const [k, v] of Object.entries(roles.colors)) if (v) lines.push(`  ${k}: ${v};`);
  for (const [k, v] of Object.entries(roles.fonts)) if (v) lines.push(`  ${k}: ${v};`);
  return `${googleFontsImport(families)}\n:root{\n${lines.join('\n')}\n}`;
}

function styleCss(styleMap) {
  return styleMap.map(([decl, c]) => `.${c}{${decl.split(';').map(d => d.trim()).filter(Boolean).map(d => /!important$/.test(d) ? d : d + ' !important').join(';')}}`).join('\n');
}

// Runtime-only selectors (Claude Design dc runtime, React host wrappers).
function dropRuntime(text) {
  let dropped = 0;
  const o = css.map(text, it => {
    if (it.kind === 'block-at' && /^@keyframes\s+sc-/i.test(it.head)) { dropped++; return ''; }
    if (it.kind !== 'rule') return undefined;
    const sels = css.selectors(it.head).map(s => s.replace(/#dc-root\b/g, 'body').replace(/^body\s+body\b/, 'body'));
    const keep = sels.filter(s => !/\bx-dc\b|\[data-dc|\.sc-(host|interp|shine)|#__bundler|\bsc-(if|for|else)\b/.test(s));
    if (!keep.length) { dropped++; return ''; }
    return `${keep.join(',')}{${it.body}}`;
  });
  return { css: o, dropped };
}

function roleWarnings(roles, report) {
  const c = roles.colors;
  const lum = h => { const [r, g, b] = hexToRgb(h); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
  const same = ['--surface', '--muted', '--border'].filter(k => c[k] && [c['--fg'], c['--bg']].includes(c[k]));
  if (same.length) report.warnings.push(`role check: ${same.join(', ')} equal --fg/--bg -- correct them from roles.ranked`);
  for (const k of ['--accent', '--accent-on', '--muted', '--border']) if (!c[k]) report.warnings.push(`role check: ${k} not detected -- set it by hand`);
  if (c['--muted'] && c['--fg'] && c['--bg'] && Math.abs(lum(c['--muted']) - lum(c['--bg'])) > Math.abs(lum(c['--fg']) - lum(c['--bg']))) {
    report.warnings.push('role check: --muted has more contrast than --fg -- they are probably swapped');
  }
}

function postCss(sourceCss, inlineCss, roles, markup, report) {
  let text = sourceCss.join('\n');
  if (split) { // print-only CSS has no place in a screen template; pt -> px
    text = css.map(text, it => (it.kind === 'block-at' && /^@(page|media\s+print)/i.test(it.head)) ? '' : undefined)
      .replace(/(?:page-break-(?:before|after|inside)|break-(?:before|after|inside))\s*:[^;}]+;?/g, '')
      .replace(/(-?\d*\.?\d+)pt\b/g, (m, n) => `${Math.round(parseFloat(n) * 4 / 3 * 10) / 10}px`);
  }
  if (kind === 'deck') {
    const neg = [...text.matchAll(/([^{}]+)\{[^}]*z-index\s*:\s*-\d+/g)].map(m => m[1].trim()).slice(0, 5);
    if (neg.length) report.warnings.push(`negative z-index inside slides (${neg.join(' | ')}): the slide frame's transform paints these above the slide background -- check those slides against the original`);
  }
  const rt = dropRuntime(text);
  text = rt.css;
  const b1 = bridgeRoot(text, roles);
  const r1 = rewriteColors(b1.css, roles);
  const before = r1.css.length;
  let deduped = css.dedupe(r1.css);
  const used = css.classesIn(markup);
  const pr = css.pruneUnused(deduped, used, STATE_CLASSES);
  const r2 = rewriteColors(inlineCss, roles);
  // inline-style classes: keep only those the markup uses
  const pr2 = css.pruneUnused(r2.css, used, STATE_CLASSES);
  report.bridged = b1.bridged;
  report.unbridged = b1.unbridged;
  report.rewritten = { source: r1.used, inline: r2.used };
  report.css = { runtime_rules_dropped: rt.dropped, source_chars_before: before, source_chars_after: pr.css.length,
    unused_rules_pruned: pr.removed + pr2.removed };
  for (const [n, t] of [['source', pr.css], ['inline', pr2.css]]) {
    const bad = css.balanced(t);
    if (bad) report.warnings.push(`${n} css: ${bad}`);
  }
  return { source: css.minify(pr.css), inline: css.minify(pr2.css) };
}

function finish(html, report, roles, fontFaces) {
  const ff = [...new Set(fontFaces.map(f => f.family))];
  report.fonts = { families: ff, embedded_faces_replaced_by_import: fontFaces.filter(f => f.embedded).length, google_import: googleFontsImport(ff) };
  report.roles = roles;
  roleWarnings(roles, report);
  report.chars = html.length;
  report.cap = 120000;
  if (html.length > 120000) report.warnings.push(`example.html is ${html.length} chars; the prompt copy is cut at 120,000 -- run trim.cjs`);
  report.external_urls = [...new Set((html.match(/https?:\/\/[^"')\s>]+/g) || []).filter(u => !/w3\.org|fonts\.(googleapis|gstatic)\.com/.test(u)))];
  report.hex_outside_root = (html.replace(/:root\s*\{[^}]*\}/g, '').match(/#[0-9a-f]{6}\b|#[0-9a-f]{3}\b/gi) || []).length;
  for (const s of report.screens || []) delete s.inner;
  for (const s of report.states || []) delete s.inner;
  fs.writeFileSync(path.join(out, 'snapshot-report.json'), JSON.stringify(report, null, 2));
  if (!html) {
    console.log(JSON.stringify(report, null, 2));
    console.error('ERROR: nothing captured -- no example.html written (see warnings)');
    process.exit(3);
  }
  fs.writeFileSync(path.join(out, 'example.html'), html);
  console.log(JSON.stringify(report, null, 2));
  if (report.failed_states) {
    console.error(`WARNING: ${report.failed_states} configured state(s) captured nothing (see warnings) -- fix their selectors`);
    process.exitCode = 4;
  }
}

/* ---------------------------------------------------------------- capture */
async function capture() {
  const browser = await chromium.launch({ channel: 'chrome' });
  const pg = await browser.newPage({ viewport: { width: vw, height: vh } });
  const errors = [];
  pg.on('pageerror', e => errors.push(String(e.message || e)));
  pg.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  const url = 'file://' + path.resolve(entry);
  let styleEntries = [];
  const saveMap = async () => { styleEntries = await pg.evaluate(() => [...window.__styleMap]).catch(() => styleEntries); };
  const load = async () => {
    await pg.goto(url, { waitUntil: 'load', timeout: 60000 });
    await pg.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
    await pg.waitForTimeout(cfg.settle || 2500);
    await pg.evaluate(installHelpers, { prefix, entries: styleEntries });
  };
  await load();
  const report = { mode: 'capture', kind, entry, viewport: [vw, vh], screens: [], states: [], errors, warnings: [] };
  const fontsFrom = async () => {
    const r = await pg.evaluate(async () => await window.__collectCss());
    fontImports.push(...r.imports);
    return r;
  };

  if (kind === 'deck') return captureDeck(pg, browser, report, fontsFrom);

  // ---- nav discovery
  let nav = [];
  try {
    nav = await pg.evaluate(({ navSel, skip }) => {
      const isIcon = e => /material|symbols|icon/i.test(getComputedStyle(e).fontFamily) || e.matches('svg, i, [class*=icon]');
      const clean = e => {
        const parts = [];
        const walk = n => {
          for (const c of n.childNodes) {
            if (c.nodeType === 3) parts.push(c.textContent);
            else if (c.nodeType === 1 && !isIcon(c) && c.tagName !== 'KBD' && !/^\s*(alt|ctrl|⌘|⌥)\s*\+?\s*\d+\s*$/i.test(c.textContent)) walk(c);
          }
        };
        walk(e);
        return parts.join(' ').replace(/\s+/g, ' ').replace(/^\d{1,2}\s+/, '').trim();
      };
      let items = [];
      if (navSel) items = [...document.querySelectorAll(navSel)];
      else {
        const navs = [...document.querySelectorAll('nav, [role=navigation], aside')]
          .filter(n => !/drawer|modal|dialog|popover|toast/i.test(n.className + ' ' + (n.getAttribute('role') || '')));
        for (const n of navs) {
          const c = [...n.querySelectorAll('button, a, [role=tab], [role=menuitem], [role=link]')].filter(x => clean(x));
          if (c.length >= 2) { items = c; break; }
        }
      }
      items = items.filter(x => !(skip || []).some(s => clean(x).toLowerCase().includes(s.toLowerCase())));
      items.forEach((x, i) => x.setAttribute('data-snap-nav', String(i)));
      const icon = x => { const i = [...x.querySelectorAll('*')].find(isIcon); return i ? i.textContent.trim() : ''; };
      return items.map((x, i) => ({ i, label: clean(x), icon: icon(x) }));
    }, { navSel: cfg.nav || null, skip: cfg.skipNav });
  } catch (e) {
    report.warnings.push(`config.nav must be a CSS selector: ${e.message.split('\n')[0]}`);
  }
  if (nav.length < 2 && !split && !(cfg.states || []).length) report.warnings.push(`found ${nav.length} nav items -- pass config.nav, config.states or --split`);
  const navWarn = () => {
    const shown = nav.length + (cfg.states || []).filter(x => x.nav).length;
    if (expectScreens && shown < expectScreens) report.warnings.push(`nav covers ${shown} of ${expectScreens} declared screens -- the rest are role-gated or hidden: add them as config.states with nav:true`);
  };

  const contentSel = cfg.content || 'main';
  const ids = new Set();
  const uniq = base => { let id = base, n = 2; while (ids.has(id)) id = `${base}-${n++}`; ids.add(id); return id; };
  let shell = null;
  const grabShell = async () => pg.evaluate(contentSel => {
    const c = document.querySelector(contentSel);
    if (!c) return null;
    const items = [...document.querySelectorAll('[data-snap-nav]')];
    const st = items.map(x => x.getAttribute('style') || '');
    const navInfo = { active: st[0] || '', inactive: st.find((s, i) => i > 0 && s !== st[0]) || st[1] || '' };
    const bodyClone = document.body.cloneNode(true);
    const cc = bodyClone.querySelector(contentSel);
    if (cc) cc.innerHTML = '__CONTENT__';
    for (const s of bodyClone.querySelectorAll('script, template, [id^=__bundler]')) s.remove();
    for (const x of bodyClone.querySelectorAll('[data-snap-nav]')) x.setAttribute('style', navInfo.inactive);
    const keep = /^data-snap-nav$/;
    return { shellHtml: window.__clean(bodyClone, keep).innerHTML, navInfo };
  }, contentSel);

  const navTo = cfg.navTo || {};
  const navTarget = report.navTarget = {}; // nav index -> state id it opens instead of its own capture
  for (const item of nav) {
    const target = Object.entries(navTo).find(([lab]) => item.label.toLowerCase() === lab.toLowerCase());
    if (target) { navTarget[String(item.i)] = slug(target[1]); continue; }
    try {
      await pg.locator(`[data-snap-nav="${item.i}"]`).first().click({ timeout: 5000 });
    } catch (e) {
      report.warnings.push(`could not click nav "${item.label}": ${e.message.split('\n')[0]}`);
      continue;
    }
    await pg.waitForTimeout(cfg.wait || 700);
    if (shell === null) shell = await grabShell();
    const got = await pg.evaluate(contentSel => {
      const c = document.querySelector(contentSel);
      if (!c) return null;
      return { inner: window.__clean(c).innerHTML, label: window.__label(c), h: c.scrollHeight };
    }, contentSel);
    if (!got) { report.warnings.push(`content area "${contentSel}" not found -- pass config.content`); break; }
    const id = uniq(slug(item.label));
    report.screens.push({ id, label: item.label, icon: item.icon, purpose: got.label, inner: got.inner, chars: got.inner.length, height: got.h });
    await pg.mouse.move(0, 0);
    await pg.waitForTimeout(150);
    await pg.screenshot({ path: path.join(out, 'shots', `${id}.png`), fullPage: true });
  }

  for (const st of cfg.states || []) {
    try {
      if (st.reset) { await saveMap(); await load(); }
      await runSteps(pg, st.steps);
      const sel = st.capture || contentSel;
      const got = await pg.evaluate(sel => {
        const e = document.querySelector(sel);
        if (!e) return null;
        const r = e.getBoundingClientRect();
        const cx = (r.left + r.right) / 2 / innerWidth, cy = (r.top + r.bottom) / 2 / innerHeight;
        const role = e.getAttribute('role') || '';
        // did the original dim the page behind it? (a fixed, near-full-viewport, semi-transparent layer)
        const scrim = [...document.querySelectorAll('body *')].some(x => {
          const cs = getComputedStyle(x); if (!/fixed|absolute/.test(cs.position) || e.contains(x)) return false;
          const b = x.getBoundingClientRect(); if (b.width < innerWidth * 0.9 || b.height < innerHeight * 0.9) return false;
          const m = cs.backgroundColor.match(/rgba\(\s*\d+[,\s]+\d+[,\s]+\d+[,\s/]+([\d.]+)/);
          return m && Number(m[1]) > 0.08 && Number(m[1]) < 0.95;
        });
        const geom = { centered: Math.abs(cx - 0.5) < 0.12 && r.width < innerWidth * 0.9, menu: /menu|listbox/.test(role) || (r.width < 420 && r.height < 520 && !/dialog/.test(role)), scrim };
        return { html: window.__clean(e).outerHTML, inner: window.__clean(e).innerHTML, label: window.__label(e), geom };
      }, sel);
      if (!got) { report.warnings.push(`state ${st.id}: capture selector ${sel} matched nothing`); report.failed_states = (report.failed_states || 0) + 1; continue; }
      const id = uniq(slug(st.id));
      // a content-area capture keeps only its children (the pattern is the content area)
      const inner = sel === contentSel ? got.inner : got.html;
      if (!st.overlay && sel !== contentSel) report.notes = (report.notes || []).concat(`state ${id}: narrow capture -- previewed with page padding`);
      report.states.push({ id, purpose: st.purpose || got.label || st.id, overlay: !!st.overlay, geom: got.geom, narrow: sel !== contentSel && !st.overlay, under: st.under || null, nav: !!st.nav,
        label: st.label || st.purpose || st.id, icon: st.icon || '', inner, chars: inner.length });
      await pg.mouse.move(0, 0);
      await pg.waitForTimeout(150);
      await pg.screenshot({ path: path.join(out, 'shots', `${id}.png`), fullPage: !st.overlay });
      if (shell === null && sel === contentSel) shell = await grabShell();
    } catch (e) {
      report.warnings.push(`state ${st.id} failed: ${e.message.split('\n')[0]}`);
      report.failed_states = (report.failed_states || 0) + 1;
    }
  }

  // --split: a document with no app frame -> one pattern per heading section
  if (split && !report.screens.length) {
    const parts = await pg.evaluate(level => {
      const root = document.querySelector('main') || document.body;
      const heads = [...root.querySelectorAll(level)];
      const out = [];
      if (!heads.length) return out;
      const firstHead = heads[0];
      const intro = [];
      for (let n = root.firstChild; n && n !== firstHead && !(n.contains && n.contains(firstHead)); n = n.nextSibling) intro.push(n);
      const wrap = nodes => { const d = document.createElement('div'); nodes.forEach(n => d.appendChild(n.cloneNode(true))); return window.__clean(d).innerHTML; };
      if (intro.length) out.push({ label: 'Overview', inner: wrap(intro) });
      for (const h of heads) {
        const nodes = [h];
        for (let n = h.nextElementSibling; n && !n.matches(level); n = n.nextElementSibling) nodes.push(n);
        const rect = nodes.reduce((r, n) => { const b = n.getBoundingClientRect(); return r ? { top: Math.min(r.top, b.top + scrollY), bottom: Math.max(r.bottom, b.bottom + scrollY) } : { top: b.top + scrollY, bottom: b.bottom + scrollY }; }, null);
        out.push({ label: h.textContent.replace(/\s+/g, ' ').trim(), inner: wrap(nodes), rect });
      }
      return out;
    }, String(split));
    for (const p of parts) {
      const id = uniq(slug(p.label));
      report.screens.push({ id, label: p.label, icon: '', purpose: p.label, inner: p.inner, chars: p.inner.length, generated: true });
      if (p.rect && p.rect.bottom > p.rect.top) {
        await pg.screenshot({ path: path.join(out, 'shots', `${id}.png`), fullPage: true,
          clip: { x: 0, y: Math.max(0, p.rect.top - 16), width: vw, height: Math.min(4000, p.rect.bottom - p.rect.top + 32) } }).catch(() => {});
      }
    }
    if (!parts.length) report.warnings.push(`--split ${split}: no ${split} headings found`);
    report.generated_frame = true;
    await pg.screenshot({ path: path.join(out, 'shots', 'document.png'), fullPage: true });
  }

  navWarn();
  const { css: sourceCss, fontFaces } = await fontsFrom();
  const roles = await pg.evaluate(() => window.__roles());
  await saveMap();
  await browser.close();
  return writePrototype(shell, nav, report, sourceCss, fontFaces, roles, styleEntries);
}

function navItemFrom(template, id, label, icon, oldLabel, oldIcon, pos) {
  let h = template.replace(/\sdata-go="[^"]*"/, '').replace(/\sdata-snap-nav="\d+"/, '').replace(/\bis-active\b/, '');
  if (oldLabel) {
    // the label is one text node of the item; the number/icon/shortcut are others
    const segs = [...h.matchAll(/>([^<]+)</g)].map(m => m[1]).filter(t => t.trim().length > 2 && !/^\s*\d+\s*$/.test(t) && oldLabel.includes(t.trim()));
    const seg = segs.sort((a, b) => b.trim().length - a.trim().length)[0];
    if (seg) h = h.replace(`>${seg}<`, `>${seg.replace(seg.trim(), esc(label))}<`);
  }
  if (oldIcon && icon && h.includes(`>${oldIcon}<`)) h = h.replace(`>${oldIcon}<`, `>${esc(icon)}<`);
  // shortcut hint and item number follow the item's position (Alt+1..9 only)
  h = h.replace(/>(\s*(?:Alt|⌥)\s*\+?\s*)\d+(\s*)</, (m, a, b) => pos <= 9 ? `>${a}${pos}${b}<` : '><');
  h = h.replace(/>(\s*)0?\d{1,2}(\s*)</, (m, a, b) => `>${a}${String(pos).padStart(2, '0')}${b}<`);
  return h.replace(/^<(\w+)/, `<$1 data-go="${id}"`);
}

function writePrototype(shell, nav, report, sourceCss, fontFaces, roles, styleMap) {
  const screens = report.screens, states = report.states;
  if (!screens.length && !states.length) {
    report.warnings.push('nothing captured');
    return finish('', report, roles, fontFaces);
  }
  const navInfo = shell && shell.navInfo;
  const activeCss = navInfo && navInfo.active
    ? `.nav-item.is-active{${navInfo.active.split(';').map(d => d.trim()).filter(d => d && !/^all\s*:/i.test(d) && !/:\s*unset$/i.test(d)).map(d => d + ' !important').join(';')}}`
    : '';
  // `under` may be given as an id or a nav label: resolve it to a screen id
  const resolveUnder = u => {
    if (!u) return screens[0] && screens[0].id;
    const k = String(u).toLowerCase();
    const hit = screens.find(x => x.id === k || x.id === slug(u) || String(x.label).toLowerCase() === k) || states.find(x => x.id === slug(u));
    if (!hit) { report.warnings.push(`under "${u}" matches no screen id or label -- the overlay previews over ${screens[0] && screens[0].id}`); return screens[0] && screens[0].id; }
    return hit.id;
  };
  const sectionFor = (s, i, isState) => {
    const cls = ['pattern'];
    if (!isState) cls.push('screen-body');
    if (s.narrow) cls.push('pattern-narrow');
    if (s.overlay) cls.push('pattern-overlay');
    if (s.overlay && s.geom && s.geom.centered) cls.push('pattern-overlay--center');
    if (s.overlay && s.geom && (s.geom.menu || !s.geom.scrim)) cls.push('pattern-overlay--menu'); // no scrim unless the original had one
    // the author must rewrite this into what the user does here (validate fails on TODO)
    const clean = t => String(t || '').replace(/&amp;/g, '&').replace(/^\s*\d{1,2}[.\s]+/, '').trim();
    const hint = [clean(s.label), clean(s.purpose)].filter((v, k, a) => v && a.indexOf(v) === k).join(' / ');
    const under = s.overlay ? ` data-under="${resolveUnder(s.under)}"` : '';
    return `<!-- PATTERN ${s.id} - TODO purpose (${esc(hint).replace(/--/g, '-')}) -->\n<section class="${cls.join(' ')}" id="pattern-${s.id}" data-pattern="${s.id}"${under}${i ? ' hidden' : ''}>\n${s.inner}\n</section>`;
  };
  // cfg.order: ids to emit first, so the most important patterns sit inside the 120,000-char prompt window
  let all = [...screens.map(s => [s, false]), ...states.map(s => [s, true])];
  if (Array.isArray(cfg.order) && cfg.order.length) {
    const rank = id => { const k = cfg.order.map(slug).indexOf(id); return k === -1 ? 1e6 : k; };
    const first = all[0];
    all = [first, ...all.slice(1).sort((a, b) => rank(a[0].id) - rank(b[0].id))];
    const unknown = cfg.order.map(slug).filter(id => !all.some(([s]) => s.id === id));
    if (unknown.length) report.warnings.push(`config.order names unknown ids: ${unknown.join(', ')}`);
  }
  const patterns = all.map(([s, isState], i) => sectionFor(s, i, isState)).join('\n\n');
  const navStates = states.filter(s => s.nav);

  let body;
  if (shell && nav.length >= 2) {
    body = shell.shellHtml;
    let k = 0, lastItem = null;
    const navTarget = report.navTarget || {};
    const capturedIdx = nav.filter(n => !navTarget[String(n.i)]).map(n => String(n.i));
    body = body.replace(/<(button|a)\b([^>]*)\bdata-snap-nav="(\d+)"([^>]*)>/g, (m, tag, a, idx, b) => {
      const s = screens[capturedIdx.indexOf(idx)];
      const id = navTarget[idx] || (s ? s.id : `screen-${idx}`);
      k++;
      let attrs = (a + b).replace(/\sdata-go="[^"]*"/, '');
      if (/class="/.test(attrs)) attrs = attrs.replace(/class="([^"]*)"/, (mm, c) => `class="${c} nav-item${k === 1 ? ' is-active' : ''}"`);
      else attrs += ` class="nav-item${k === 1 ? ' is-active' : ''}"`;
      return `<${tag}${attrs} data-go="${id}">`;
    });
    // nav items for role-only states: clone the last nav item's markup
    if (navStates.length) {
      const items = [...body.matchAll(/<(button|a)\b[^>]*\bdata-go="[^"]*"[^>]*>[\s\S]*?<\/\1>/g)];
      lastItem = items[items.length - 1];
      if (lastItem) {
        const tpl = lastItem[0];
        const last = nav[nav.length - 1];
        const extra = navStates.map((s, k) => navItemFrom(tpl, s.id, s.label, s.icon, last.label, last.icon, nav.length + k + 1)).join('');
        body = body.slice(0, lastItem.index + tpl.length) + extra + body.slice(lastItem.index + tpl.length);
      }
    }
    body = body.replace('__CONTENT__', '\n' + patterns + '\n');
  } else {
    // generated frame: brand bar + nav + main (states-only captures and documents)
    report.generated_frame = true;
    const items = [...screens, ...states.filter(s => s.nav || !screens.length)];
    const navHtml = items.map((s, i) => `<button type="button" class="nav-item${i ? '' : ' is-active'}" data-go="${s.id}">${esc(s.label)}</button>`).join('\n');
    body = `<header class="tf-bar"><span class="tf-brand">${esc(title || 'Template')}</span></header>
<div class="tf-frame">
<nav class="tf-nav" aria-label="Sections">
${navHtml}
</nav>
<main class="tf-main">
${patterns}
</main>
</div>`;
  }

  const inlineCss = styleCss(styleMap);
  const pc = postCss(sourceCss, inlineCss, roles, body, report);
  const frameCss = `
section.pattern[hidden]{display:none !important}
.nav-item{cursor:pointer}
${activeCss}
.pattern-overlay{position:fixed;inset:0;z-index:900;background:color-mix(in srgb,var(--fg) 40%,transparent);pointer-events:none}
.pattern-overlay>*{pointer-events:auto}
.pattern-overlay[hidden]{display:none !important}
.pattern-overlay--center{display:grid !important;place-items:center}
.pattern-overlay--center>*{position:relative !important;inset:auto !important;transform:none !important;margin:0 !important}
.pattern-overlay--menu{background:transparent}
.pattern-narrow{padding:24px}
${report.generated_frame ? `body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--font-body)}
.tf-bar{display:flex;align-items:center;height:56px;padding:0 24px;background:var(--surface);border-bottom:1px solid var(--border)}
.tf-brand{font-family:var(--font-display);font-weight:700}
.tf-frame{display:flex;min-height:calc(100vh - 56px)}
.tf-nav{width:240px;flex:none;padding:16px 8px;border-right:1px solid var(--border);background:var(--surface);display:flex;flex-direction:column;gap:2px}
.tf-nav .nav-item{all:unset;display:block;padding:10px 12px;border-radius:6px;color:var(--fg);font:inherit;cursor:pointer}
.tf-nav .nav-item:hover{background:var(--bg)}
.tf-nav .nav-item.is-active{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent);font-weight:600}
.tf-main{flex:1;min-width:0;padding:32px;max-width:1100px}` : ''}`;
  const html = `<!doctype html>
<html lang="${roles.lang || 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title || 'Template')}</title>
<style>
${rootBlock(roles, fontFaces.map(f => f.family))}
</style>
<style>
/* source stylesheet (captured from the rendered page; deduped, unused rules pruned) */
${pc.source}
</style>
<style>
/* frame: one pattern visible at a time (preview only) */
${frameCss}
</style>
${pc.inline ? `<style>
/* inline styles from the source, as shared classes */
${pc.inline}
</style>` : ''}
</head>
<body>
${body}
<script>
/* preview runtime: nav switches the visible pattern; Alt+1..9 jumps */
(function(){
  var items=[].slice.call(document.querySelectorAll('.nav-item[data-go]'));
  function show(id){
    var p=document.querySelector('section.pattern[data-pattern="'+id+'"]'),under=p&&p.getAttribute('data-under');
    [].forEach.call(document.querySelectorAll('section.pattern[data-pattern]'),function(s){var k=s.getAttribute('data-pattern');s.hidden=k!==id&&k!==under;});
    var nav=under||id;
    items.forEach(function(i){i.classList.toggle('is-active',i.getAttribute('data-go')===nav);});
  }
  window.__show=show;
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){var o=document.querySelector('section.pattern-overlay:not([hidden])');if(o)show(o.getAttribute('data-under'));}});
  document.addEventListener('click',function(e){var o=e.target.closest&&e.target.closest('section.pattern-overlay');if(o&&e.target===o)show(o.getAttribute('data-under'));});
  items.forEach(function(i){i.addEventListener('click',function(e){e.preventDefault();show(i.getAttribute('data-go'));});});
  document.addEventListener('keydown',function(e){if(e.altKey&&/^[1-9]$/.test(e.key)&&items[e.key-1]){e.preventDefault();items[e.key-1].click();}});
})();
</script>
</body>
</html>
`;
  return finish(html, report, roles, fontFaces);
}

async function captureDeck(pg, browser, report, fontsFrom) {
  // 1. screenshots of the ORIGINAL, slide by slide
  const count = await pg.evaluate(() => {
    const stage = document.querySelector('deck-stage');
    let list = stage ? [...stage.children].filter(e => e.tagName === 'SECTION' || e.hasAttribute('data-om-slide-id')) : [];
    if (!list.length) list = [...document.querySelectorAll('section.slide')];
    if (!list.length) list = [...document.querySelectorAll('.slide')];
    if (!list.length) list = [...document.querySelectorAll('[data-om-slide-id]')];
    list.forEach((s, i) => s.setAttribute('data-snap-slide', String(i)));
    return list.length;
  });
  for (let i = 0; i < count; i++) {
    await pg.screenshot({ path: path.join(out, 'shots', `slide-${String(i + 1).padStart(2, '0')}.png`) });
    await pg.keyboard.press('ArrowRight');
    await pg.waitForTimeout(450);
  }
  // 2. capture
  const res = await pg.evaluate(() => {
    const list = [...document.querySelectorAll('[data-snap-slide]')];
    const host = document.querySelector('deck-stage') || (list[0] && list[0].parentElement) || document.body;
    const hostCs = getComputedStyle(host);
    const slides = list.map((s, i) => {
      s.style.removeProperty('display'); s.style.removeProperty('visibility'); s.style.removeProperty('opacity');
      const bg = getComputedStyle(s).backgroundColor;
      const label = window.__label(s) || `Slide ${i + 1}`;
      const c = window.__clean(s);
      return { label: label.slice(0, 60), inner: c.innerHTML, cls: c.className, bg };
    });
    // the deck frame inherits the font/colour the source's slides actually render with
    const ref = getComputedStyle(list[0] || document.body); // what un-fonted slide children inherit
    return { slides, hostFont: ref.fontFamily || hostCs.fontFamily, hostColor: ref.color || hostCs.color };
  });
  const slides = res.slides;
  if (!slides.length) report.warnings.push('no slides found -- pass --keep, or treat it as a prototype');
  const { css: sourceCss, fontFaces } = await fontsFrom();
  // roles across ALL slides: reveal them (stacked) for the measurement only
  const roles = await pg.evaluate(() => {
    const list = [...document.querySelectorAll('[data-snap-slide]')];
    const host = list[0] && list[0].parentElement;
    if (host) host.setAttribute('data-snap-host', '');
    list.forEach(s => { s.style.setProperty('display', 'block', 'important'); s.style.setProperty('visibility', 'visible', 'important'); s.style.setProperty('position', 'relative', 'important'); });
    return window.__roles('[data-snap-host]', '[data-snap-slide="0"]');
  });
  const styleMap = await pg.evaluate(() => [...window.__styleMap]);
  await browser.close();

  report.slides = slides.map((s, i) => ({ n: i + 1, label: s.label, chars: s.inner.length }));
  const m = slides[0] && String(slides[0].bg).match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/);
  if (m && !(m[4] !== undefined && Number(m[4]) < 0.99)) roles.colors['--bg'] = '#' + [m[1], m[2], m[3]].map(x => Number(x).toString(16).padStart(2, '0')).join('');
  // Source selectors written against the original deck container must hit ours,
  // without raising specificity above what the source had.
  const retarget = t => css.map(t, it => {
    if (it.kind !== 'rule' || !/deck-stage/.test(it.head)) return undefined;
    const sels = css.selectors(it.head).map(s => s
      .replace(/deck-stage\s*>\s*section/g, ':where(.deck > section.slide)')
      .replace(/(^|[\s>+~])deck-stage(?![\w-])/g, '$1:where(.deck)'));
    return `${sels.join(',')}{${it.body}}`;
  });
  const retargeted = sourceCss.map(retarget);
  report.retargeted = retargeted.some(t => t.includes(':where(.deck'));
  const sections = slides.map((s, i) => `<!-- SLIDE ${i + 1} - ${esc(s.label).replace(/--/g, '-')} -->\n<section class="slide ${s.cls || ''}" data-label="${esc(s.label)}">\n${s.inner}\n</section>`).join('\n\n');
  const pc = postCss(retargeted, styleCss(styleMap), roles, `<div class="deck">${sections}</div>`, report);
  const html = `<!doctype html>
<html lang="${roles.lang || 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title || 'Deck')}</title>
<style>
${rootBlock(roles, fontFaces.map(f => f.family))}
</style>
<style>
/* deck frame: 1920x1080 slides, scaled to fit, one visible at a time */
html,body{margin:0;height:100%;background:#000;overflow:hidden}
.deck{position:fixed;inset:0;font-family:${res.hostFont};color:${res.hostColor}}
.deck>section.slide{position:absolute;left:50%;top:50%;width:1920px;height:1080px;box-sizing:border-box;overflow:hidden;
  transform:translate(-50%,-50%) scale(var(--deck-scale,1));display:none;background:var(--bg)}
.deck>section.slide.active{display:block}
@media print{html,body{overflow:visible;background:none}.deck{position:static}
  .deck>section.slide{position:relative;left:0;top:0;transform:none;display:block;page-break-after:always}}
</style>
<style>
/* source stylesheet (captured from the rendered deck; deduped, unused rules pruned) */
${pc.source}
</style>
${pc.inline ? `<style>
/* inline styles from the source, as shared classes */
${pc.inline}
</style>` : ''}
</head>
<body>
<div class="deck">
${sections}
</div>
<script>
/* deck navigation: arrows / PageUp / PageDown / Space / Home / End, #<n> deep links */
(function(){
  var slides=[].slice.call(document.querySelectorAll('.deck>section.slide')),i=0;
  function fit(){var s=Math.min(innerWidth/1920,innerHeight/1080);document.documentElement.style.setProperty('--deck-scale',s);}
  function go(n){i=Math.max(0,Math.min(slides.length-1,n));slides.forEach(function(s,k){s.classList.toggle('active',k===i);});
    if(location.hash!=='#'+(i+1))history.replaceState(null,'','#'+(i+1));}
  addEventListener('resize',fit);fit();
  addEventListener('keydown',function(e){
    if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();go(i+1);}
    else if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){e.preventDefault();go(i-1);}
    else if(e.key==='Home'){go(0);}else if(e.key==='End'){go(slides.length-1);}});
  addEventListener('click',function(e){if(!e.target.closest('a,button,input,select,textarea'))go(i+(e.clientX>innerWidth/2?1:-1));});
  go((parseInt(location.hash.slice(1),10)||1)-1);
})();
</script>
</body>
</html>
`;
  return finish(html, report, roles, fontFaces);
}

if (arg('keep')) keepMode();
else capture().catch(e => { console.error(e); process.exit(1); });
