#!/usr/bin/env node
/*
 * Shrink a draft example.html toward the 120,000-char prompt cap WITHOUT
 * deleting meaning: only long runs of repeated siblings are shortened.
 *
 *   node trim.cjs <example.html> [--budget 120000] [--out <file>] [--floor 5] [--keep <css>]... [--force]
 *
 * If even the deepest round cannot bring the file under --budget, the content
 * trim is NOT applied (only the lossless pass is written) unless --force: losing
 * rows without reaching the budget buys nothing. --keep <css> pins elements
 * (and the run items containing them) that must never be trimmed, e.g. an exit
 * row: --keep '.ib-seatrow:has(.ib-seatrow__exit:not(.ib-seatrow__exit--none))'.
 *
 * First a lossless pass (whitespace collapse outside pre/textarea/script/style,
 * HTML comments dropped except PATTERN / SLIDE / trimmed markers, CSS minified).
 * Then rules applied in rounds, mildest first, stopping as soon as the file fits:
 *   - a "run" is >= 2 consecutive sibling elements with the same tag and the
 *     same class list (table rows, list items, cards, seats, chips, log lines)
 *   - round 1 keeps 8 of runs longer than 12; round 2 keeps 6 of runs longer
 *     than 8; round 3 keeps --floor (default 5) of runs longer than --floor+1.
 *     A run of --floor items or fewer is NEVER touched.
 *   - never trimmed: patterns and slides themselves, unclassed <div>/<span>
 *     runs (only <tr>, <li> and classed siblings are candidates), steppers, tabs, tab lists, breadcrumbs, pagination,
 *     legends, KPI/stat rows, filters/chips toolbars, nav and menus, <select>
 *     options, table header rows, anything inside <svg> or <nav>
 *   - also never removed: header rows (role=row first row, columnheader cells,
 *     uppercase label rows), items carrying a state or marker (selected,
 *     current, blocked, exit, warning, aria-selected, checked ...), and a
 *     trailing "N more" / total summary row
 *   - headings in the same pattern that state the run's original length are
 *     listed in heading_claims_to_fix
 *   - a trimmed run ends with <!-- trimmed: N more like the above --> so the
 *     builder knows the list continues
 *   - after the DOM pass, CSS rules for classes no longer used are pruned
 * Writes --out (default: OVERWRITES the input -- keep a copy, or pass --out) and prints a JSON report with
 * every trimmed run (pattern, selector, kept/removed). Fix any visible count
 * ("16 shown") that the trimmed list now contradicts.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const css = require('./css_tools.cjs');
const REPO = path.resolve(__dirname, '../../../..');
let chromium;
try { ({ chromium } = require(path.join(REPO, 'frontend/node_modules/playwright'))); }
catch (e) { ({ chromium } = require('playwright')); }

const argv = process.argv;
const opt = (n, d) => { const i = argv.indexOf('--' + n); return i > -1 ? argv[i + 1] : d; };
const file = path.resolve(argv[2]);
const budget = Number(opt('budget', 120000));
const floor = Number(opt('floor', 5));
const outFile = path.resolve(opt('out', file));
const force = argv.includes('--force');
const keepSel = []; argv.forEach((a, i) => { if (a === '--keep') keepSel.push(argv[i + 1]); });
// @import url('...css2?family=A:wght@400;500&display=swap'); -- the URL itself contains ';'
const IMPORT_RE = /@import\s+(?:url\(\s*(?:'[^']*'|"[^"]*"|[^)]*)\s*\)|'[^']*'|"[^"]*")[^;]*;/g;

// Lossless shrink: drop non-marker comments, collapse whitespace outside pre/textarea/script/style.
function lossless(html) {
  const keep = /<(pre|textarea|script|style)\b[\s\S]*?<\/\1>/gi;
  let out = '', last = 0;
  const squeeze = seg => seg
    .replace(/<!--(?!\s*(PATTERN|SLIDE|trimmed))[\s\S]*?-->/g, '')
    .replace(/>\s*\n\s*/g, '>\n').replace(/[ \t]{2,}/g, ' ').replace(/\n{2,}/g, '\n');
  for (const m of html.matchAll(keep)) {
    out += squeeze(html.slice(last, m.index));
    let block = m[0];
    if (/^<style/i.test(block)) {
      block = block.replace(/(<style[^>]*>)([\s\S]*?)(<\/style>)/i, (x, a, t, b) => {
        const imports = (t.match(IMPORT_RE) || []).join('\n');
        return a + (imports ? imports + '\n' : '') + css.minify(t.replace(IMPORT_RE, '')) + b;
      });
    }
    out += block;
    last = m.index + m[0].length;
  }
  return out + squeeze(html.slice(last));
}

const STATE = /^(is-|has-)|^(active|open|show|shown|hidden|selected|current|disabled|expanded|collapsed|checked|visible|on|off)$/;

(async () => {
  const original = fs.readFileSync(file, 'utf8');
  const src = lossless(original);
  const report = { file, budget, before: original.length, after_lossless: src.length, rounds: [], trimmed: [] };
  if (src.length <= budget) {
    fs.writeFileSync(outFile, src);
    report.after = src.length;
    report.note = 'already within budget';
    console.log(JSON.stringify(report, null, 2));
    return;
  }
  const browser = await chromium.launch({ channel: 'chrome' });
  // load without running scripts or fetching anything, so the DOM is exactly the file
  const ctx = await browser.newContext({ javaScriptEnabled: false });
  const pg = await ctx.newPage();
  await pg.route('**/*', r => r.request().resourceType() === 'document' ? r.continue() : r.abort());
  const tmp = outFile + '.trim-src.html';
  fs.writeFileSync(tmp, src);
  await pg.goto('file://' + tmp);
  const rounds = [[12, 8], [8, 6], [floor + 1, floor]];
  let html = src;
  for (const [over, keep] of rounds) {
    const res = await pg.evaluate(({ over, keep, keepSel }) => {
      const pinned = new Set(keepSel.flatMap(sel => { try { return [...document.querySelectorAll(sel)]; } catch (e) { return []; } }));
      const PROTECT = /step|stepper|progress|wizard|tab|breadcrumb|pagination|pager|legend|kpi|stat|metric|tile|filter|toolbar|segment|chip-group|nav|menu|swatch|head|header|thead|columnheader|caption/i;
      const isProtected = el => {
        for (let n = el; n && n !== document.body; n = n.parentElement) {
          if (/^(NAV|SVG|SELECT|THEAD|OL|HEAD)$/i.test(n.tagName)) return n.tagName !== 'OL' || PROTECT.test(n.className);
          const r = n.getAttribute && (n.getAttribute('role') || '');
          if (/tablist|menu|menubar|navigation|radiogroup|toolbar|columnheader|rowheader/.test(r)) return true;
          if (n.getAttribute && n.getAttribute('aria-label') && /step|progress/i.test(n.getAttribute('aria-label'))) return true;
          if (n !== el.parentElement && n !== el) continue;
          if (PROTECT.test(String(n.className || ''))) return true;
        }
        return false;
      };
      // a header row: the first row of a grid/table-like block whose cells are short labels
      const isHeaderRow = p => {
        const r = p.getAttribute('role') || '';
        if (r === 'row' && (p.querySelector('[role=columnheader]') || p === p.parentElement.firstElementChild)) return true;
        const kids = [...p.children];
        if (kids.length < 3) return false;
        const labels = kids.filter(k => k.children.length === 0 && k.textContent.trim().length > 0 && k.textContent.trim().length < 28);
        const labelish = labels.some(k => /micro|label|caption|eyebrow|overline|head/i.test(k.className) || /uppercase/.test(getComputedStyle(k).textTransform || ''));
        return labels.length >= 0.7 * kids.length && labelish;
      };
      // items that carry meaning beyond "one more row": a state, a selection, a special marker
      const SPECIAL = /(^|[-_])(selected|current|active|blocked|exit|special|warning|critical|error|danger|prm|assist|highlight|flag|alert|locked)(\b|[-_]|$)/i;
      // marker tokens an item carries (classes like ib-seat--selected, aria-selected, checked)
      const markers = e => {
        const t = new Set();
        for (const n of [e, ...e.querySelectorAll('*')]) {
          const cls = String(n.className && n.className.baseVal !== undefined ? n.className.baseVal : n.className || '');
          for (const c of cls.split(/\s+/)) if (SPECIAL.test(c) && !/(--|-|_)(none|off|empty|placeholder)$/.test(c)) t.add(c);
          if (n.getAttribute('aria-selected') === 'true') t.add('aria-selected');
          if (n.getAttribute('aria-current')) t.add('aria-current');
          if (n.hasAttribute('checked')) t.add('checked');
        }
        return t;
      };
      let runMarkers = null;
      // an item is special when it carries a marker that at most half of its run carries
      const special = e => { const m = markers(e); if (!runMarkers) return m.size > 0; return [...m].some(c => (runMarkers.get(c) || 0) <= runMarkers.size_ / 2); };
      const isSummary = e => /\b\d[\d,.]*\s+more\b|\btotal\b|\bsubtotal\b/i.test(e.textContent || '');
      const sig = e => e.tagName + '|' + [...e.classList].filter(c => !/^(is-|has-)|^(active|selected|current|open)$/.test(c)).sort().join('.');
      const trimmed = [];
      const parents = new Set([...document.querySelectorAll('body *')].map(e => e.parentElement).filter(Boolean));
      for (const p of parents) {
        if (isHeaderRow(p)) continue;
        const kids = [...p.children];
        let i = 0;
        while (i < kids.length) {
          let j = i + 1;
          while (j < kids.length && sig(kids[j]) === sig(kids[i])) j++;
          const run = kids.slice(i, j);
          const r0 = run[0];
          const eligible = !r0.hasAttribute('data-pattern') && !r0.classList.contains('slide') && !r0.classList.contains('pattern')
            && r0.tagName !== 'SECTION' && (/^(TR|LI)$/.test(r0.tagName) || r0.classList.length > 0)
            && !r0.matches('th, [role=columnheader]')
            // controls are choices (code pills, filters, options): every one is meaningful
            && !(r0.matches('button, [role=button], [role=option], [role=radio], label, input, a') && run.length <= 16);
          // cells of one grid/flex row (short leaf items filling the parent) are columns, not rows
          const pd = getComputedStyle(p).display;
          const cells = /grid|flex|table-row/.test(pd) && run.length === kids.length && run.every(e => e.querySelectorAll('*').length <= 2 && e.textContent.trim().length < 40);
          if (run.length > over && eligible && !cells && !isProtected(r0)) {
            // keep the first `keep` plain items, every special item, and a trailing summary row
            runMarkers = new Map();
            runMarkers.size_ = run.length;
            run.forEach(e => markers(e).forEach(c => runMarkers.set(c, (runMarkers.get(c) || 0) + 1)));
            const keepSet = new Set(run.slice(0, keep));
            run.forEach(e => { if (special(e) || pinned.has(e) || [...pinned].some(x => e.contains(x))) keepSet.add(e); });
            const summary = isSummary(run[run.length - 1]) ? run[run.length - 1] : null;
            if (summary) keepSet.add(summary);
            const drop = run.filter(e => !keepSet.has(e));
            if (drop.length) {
              const pat = r0.closest('[data-pattern], section.slide');
              // a heading that states the run's full length now overstates it
              const scope = r0.closest('[data-pattern]') || document.body;
              const claims = [...scope.querySelectorAll('h1,h2,h3,h4,h5,[class*=title],[class*=head]')]
                .map(h => h.textContent.replace(/\s+/g, ' ').trim()).filter(t => new RegExp('(^|\\D)' + run.length + '(\\D|$)').test(t)).slice(0, 3);
              // a kept "N more" summary now under-counts: it must grow by the rows removed
              if (summary) claims.push(`summary row "${summary.textContent.replace(/\s+/g, ' ').trim().slice(0, 80)}" -- add ${drop.length} to its count`);
              trimmed.push({ pattern: pat ? (pat.getAttribute('data-pattern') || pat.getAttribute('data-label')) : null, selector: sig(r0).replace('|', '.'),
                run: run.length, kept: run.length - drop.length, removed: drop.length, kept_special: [...keepSet].filter(special).length, heading_claims: claims });
              runMarkers = null;
              const last = drop[drop.length - 1];
              last.after(document.createComment(` trimmed: ${drop.length} more like the above `));
              drop.forEach(d => d.remove());
            }
          }
          i = j;
        }
      }
      return { trimmed, html: '<!doctype html>\n' + document.documentElement.outerHTML };
    }, { over, keep, keepSel });
    html = res.html;
    report.trimmed.push(...res.trimmed);
    // prune CSS that no longer matches any class in the markup
    const body = html.split(/<body\b/)[1] || html;
    const used = css.classesIn(body);
    let pruned = 0;
    html = html.replace(/(<style[^>]*>)([\s\S]*?)(<\/style>)/g, (m, a, t, b) => {
      const imports = (t.match(IMPORT_RE) || []).join('\n');
      const rest = t.replace(IMPORT_RE, '');
      const pr = css.pruneUnused(rest, used, STATE);
      pruned += pr.removed;
      return a + (imports ? imports + '\n' : '') + css.minify(pr.css) + b;
    });
    report.rounds.push({ over, keep, runs: res.trimmed.length, chars: html.length, css_rules_pruned: pruned });
    if (html.length <= budget) break;
  }
  await browser.close();
  fs.unlinkSync(tmp);
  html = lossless(html);
  // trimming that cannot reach the budget only costs fidelity: keep the lossless file instead
  if (html.length > budget && !force) {
    report.reverted = `even trimmed (${html.length} chars) the file is over budget, so content trimming was NOT applied; only the lossless pass was kept. Narrow the captures (see SKILL.md) or pass --force to keep the trimmed version.`;
    report.would_trim = report.trimmed;
    report.trimmed = [];
    html = src;
  }
  fs.writeFileSync(outFile, html);
  report.patterns_beyond_cap = [...html.matchAll(/<section[^>]*data-pattern="([^"]+)"/g)].filter(m => m.index > budget).map(m => m[1]);
  report.heading_claims_to_fix = report.trimmed.filter(t => t.heading_claims && t.heading_claims.length);
  report.after = fs.readFileSync(outFile, 'utf8').length; // the written file, the number to quote
  report.within_budget = html.length <= budget;
  if (!report.within_budget) report.note = `still ${html.length} chars at floor ${floor}. Patterns past the cap (builders never see them in the prompt): ${report.patterns_beyond_cap.join(', ') || 'none'}. Re-capture big states with a narrow \`capture\` selector (only the part that changes), drop near-duplicate patterns, or shorten by hand by the same rules.`;
  report.check_counts = 'search the trimmed patterns for visible totals ("N shown", "of N") and keep them truthful';
  console.log(JSON.stringify(report, null, 2));
})().catch(e => { console.error(e); process.exit(1); });
