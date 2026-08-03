"""The stylesheet and the script, inlined into every page. No logic lives here.

Both are string constants because a page must open by double-click from
`file://`: no external stylesheet, no CDN, no bundler, and no `fetch()` — the
browser blocks that against a file origin, which would break the one way these
reports are actually opened.

The script sorts, filters, expands and deep-links. It computes no score. Every
number on the page was produced by Python, because two implementations of the
grade arithmetic is the exact bug this harness exists to catch.
"""

from __future__ import annotations

# Applied before first paint so a dark-theme reader never sees a white flash.
THEME_BOOTSTRAP = """
(function () {
  try {
    var saved = localStorage.getItem('grading-theme');
    if (saved) { document.documentElement.setAttribute('data-theme', saved); }
  } catch (e) { /* private mode: fall back to the media query */ }
})();
"""

CSS = """
:root {
  --bg: #ffffff; --panel: #f7f8fa; --panel-2: #eef0f4; --ink: #1c1f24;
  --muted: #5b6472; --line: #d8dde5; --accent: #2f6fdb; --accent-ink: #ffffff;
  --ok: #1d7a44; --ok-bg: #dcf3e5; --warn: #8a6100; --warn-bg: #fdf1cf;
  --bad: #b4231f; --bad-bg: #fbdedd; --code-bg: #f2f4f7;
  --radius: 8px; --gap: 16px;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          Helvetica, Arial, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171c; --panel: #1b1f26; --panel-2: #232833; --ink: #e6e9ef;
    --muted: #98a2b3; --line: #2f3642; --accent: #6ea8ff; --accent-ink: #0b1220;
    --ok: #6ee7a8; --ok-bg: #16351f; --warn: #f0c674; --warn-bg: #3a2f12;
    --bad: #ff8a84; --bad-bg: #3d1a19; --code-bg: #10131a;
  }
}
:root[data-theme="light"] {
  --bg: #ffffff; --panel: #f7f8fa; --panel-2: #eef0f4; --ink: #1c1f24;
  --muted: #5b6472; --line: #d8dde5; --accent: #2f6fdb; --accent-ink: #ffffff;
  --ok: #1d7a44; --ok-bg: #dcf3e5; --warn: #8a6100; --warn-bg: #fdf1cf;
  --bad: #b4231f; --bad-bg: #fbdedd; --code-bg: #f2f4f7;
}
:root[data-theme="dark"] {
  --bg: #14171c; --panel: #1b1f26; --panel-2: #232833; --ink: #e6e9ef;
  --muted: #98a2b3; --line: #2f3642; --accent: #6ea8ff; --accent-ink: #0b1220;
  --ok: #6ee7a8; --ok-bg: #16351f; --warn: #f0c674; --warn-bg: #3a2f12;
  --bad: #ff8a84; --bad-bg: #3d1a19; --code-bg: #10131a;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: var(--sans); font-size: 14px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1400px; margin: 0 auto; padding: 0 20px 64px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { line-height: 1.25; margin: 0 0 8px; }
h1 { font-size: 22px; } h2 { font-size: 17px; } h3 { font-size: 14px; }
p { margin: 0 0 10px; }
code, .mono { font-family: var(--mono); font-size: 0.92em; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* header ------------------------------------------------------------- */
header.top {
  position: sticky; top: 0; z-index: 20; background: var(--bg);
  border-bottom: 1px solid var(--line); padding: 12px 0 0;
}
header.top .inner {
  max-width: 1400px; margin: 0 auto; padding: 0 20px;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.crumbs { color: var(--muted); font-size: 12px; }
.crumbs a { color: var(--muted); }
.spacer { flex: 1 1 auto; }
button.ghost {
  background: var(--panel); color: var(--ink); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 5px 10px; cursor: pointer;
  font: inherit; font-size: 12px;
}
button.ghost:hover { background: var(--panel-2); }

/* tabs --------------------------------------------------------------- */
nav.tabs {
  display: flex; gap: 2px; overflow-x: auto; max-width: 1400px;
  margin: 10px auto 0; padding: 0 20px;
}
nav.tabs button {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted); padding: 8px 12px; cursor: pointer; font: inherit;
  white-space: nowrap; font-size: 13px;
}
nav.tabs button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); }
.tabpanel { display: none; padding-top: 20px; }
.tabpanel.active { display: block; }

/* panels and grids --------------------------------------------------- */
section.card {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 16px; margin: 0 0 var(--gap);
}
.grid { display: grid; gap: var(--gap); }
.cols-2 { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.stats { display: flex; flex-wrap: wrap; gap: 10px; }
.stat {
  background: var(--bg); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 10px 14px; min-width: 130px; flex: 1 1 130px;
}
.stat .label { color: var(--muted); font-size: 11px; text-transform: uppercase;
               letter-spacing: .04em; }
.stat .value { font-size: 20px; font-weight: 650; font-variant-numeric: tabular-nums; }

/* the grade hero ----------------------------------------------------- */
.hero { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.grade-badge {
  font-size: 40px; font-weight: 700; letter-spacing: -.02em; line-height: 1;
  padding: 14px 20px; border-radius: var(--radius); min-width: 110px; text-align: center;
}
.grade-score { font-size: 26px; font-weight: 650; font-variant-numeric: tabular-nums; }
.g-high { background: var(--ok-bg); color: var(--ok); }
.g-mid  { background: var(--warn-bg); color: var(--warn); }
.g-low  { background: var(--bad-bg); color: var(--bad); }

/* tables ------------------------------------------------------------- */
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--line);
         vertical-align: top; }
thead th {
  background: var(--panel-2); position: sticky; top: 0; white-space: nowrap;
  font-weight: 600; font-size: 12px;
}
th.sortable { cursor: pointer; user-select: none; }
th.sortable::after { content: " ⇅"; color: var(--muted); font-size: 10px; }
th.sortable[data-dir="asc"]::after { content: " ↑"; color: var(--accent); }
th.sortable[data-dir="desc"]::after { content: " ↓"; color: var(--accent); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:hover { background: var(--panel-2); }
tr.detail > td { background: var(--bg); }
tr.hidden, .hidden { display: none; }

/* pills and badges --------------------------------------------------- */
.pill {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums;
}
.pill.high { background: var(--ok-bg); color: var(--ok); }
.pill.mid { background: var(--warn-bg); color: var(--warn); }
.pill.low { background: var(--bad-bg); color: var(--bad); }
.pill.flat { background: var(--panel-2); color: var(--muted); }
.badge {
  display: inline-block; padding: 0 6px; border-radius: 4px; font-size: 11px;
  border: 1px solid var(--line); color: var(--muted); background: var(--bg);
}
.badge.reference { border-color: var(--accent); color: var(--accent); }
.badge.copy, .badge.partial { border-color: var(--warn); color: var(--warn); }
.badge.error { border-color: var(--bad); color: var(--bad); }

/* callouts ----------------------------------------------------------- */
.callout { border-left: 3px solid var(--muted); padding: 8px 12px; margin: 0 0 12px;
           background: var(--panel-2); border-radius: 0 var(--radius) var(--radius) 0; }
.callout.bad { border-left-color: var(--bad); background: var(--bad-bg); color: var(--bad); }
.callout.warn { border-left-color: var(--warn); background: var(--warn-bg); color: var(--warn); }
.callout.info { border-left-color: var(--accent); }
.muted { color: var(--muted); }
.small { font-size: 12px; }

/* controls ----------------------------------------------------------- */
.controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 0 0 10px; }
.chip {
  border: 1px solid var(--line); background: var(--bg); color: var(--muted);
  border-radius: 999px; padding: 3px 11px; cursor: pointer; font: inherit; font-size: 12px;
}
.chip[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink);
                             border-color: var(--accent); }
input[type="search"], select {
  background: var(--bg); color: var(--ink); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 5px 9px; font: inherit; font-size: 13px;
}
.count { color: var(--muted); font-size: 12px; }

/* code, previews, diffs ---------------------------------------------- */
pre.block {
  background: var(--code-bg); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 10px; margin: 0 0 10px; overflow: auto; max-height: 460px;
  white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--mono);
  font-size: 12px; line-height: 1.45;
}
iframe.preview {
  width: 100%; height: 520px; border: 1px solid var(--line);
  border-radius: var(--radius); background: #fff;
}
.diff { font-family: var(--mono); font-size: 12px; }
.diff .add { background: var(--ok-bg); color: var(--ok); display: block; }
.diff .del { background: var(--bad-bg); color: var(--bad); display: block; }
.diff .ctx { color: var(--muted); display: block; }

/* matrix ------------------------------------------------------------- */
table.matrix td { text-align: center; font-variant-numeric: tabular-nums; padding: 4px 6px; }
table.matrix td.cell { cursor: pointer; }
table.matrix td.na { color: var(--line); }
.kind { font-size: 10px; display: block; line-height: 1; }

/* charts ------------------------------------------------------------- */
svg.chart { max-width: 100%; height: auto; display: block; }
svg.chart text { fill: var(--muted); font-family: var(--sans); font-size: 10px; }
svg.chart .axis { stroke: var(--line); }
svg.chart .series { fill: none; stroke: var(--accent); stroke-width: 2; }
svg.chart .point { fill: var(--accent); }
svg.chart .refline { stroke: var(--ok); stroke-dasharray: 4 3; stroke-width: 1.5; }
svg.chart .bar { fill: var(--accent); }

details > summary { cursor: pointer; padding: 4px 0; }
details > summary::marker { color: var(--muted); }

/* section headings that carry their own count ------------------------- */
.sechead {
  display: flex; align-items: center; gap: 8px; margin: 0 0 4px;
  font-size: 14px; font-weight: 650;
}

/* phase tabs: a segmented control, not a row of loose chips ----------- */
.phasetabs {
  display: flex; gap: 4px; flex-wrap: wrap; margin: 0 0 14px;
  border-bottom: 1px solid var(--line); padding-bottom: 10px;
}
.phasetabs button {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--bg); color: var(--muted); font: inherit; font-size: 13px;
  border: 1px solid var(--line); border-radius: var(--radius);
  padding: 6px 10px; cursor: pointer;
}
.phasetabs button:hover { background: var(--panel-2); color: var(--ink); }
.phasetabs button[aria-pressed="true"] {
  background: var(--panel-2); color: var(--ink); border-color: var(--accent);
  box-shadow: inset 0 -2px 0 var(--accent);
}
.tabcount { display: inline-flex; gap: 4px; }
.tabcount .pill { padding: 0 6px; font-size: 11px; }

/* a run panel reads as a document, so give its blocks rhythm ---------- */
.runhead { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.runhead h1 { margin: 0; }
.backlink { display: inline-block; margin: 0 0 10px; font-size: 13px; }
section.card > h2:first-child, section.card > .sechead:first-child { margin-top: 0; }

/* long text must never set the height of a page ---------------------- */
pre.block.brief { max-height: 180px; }
.tablewrap { max-height: 620px; overflow-y: auto; }
td { max-width: 640px; overflow-wrap: anywhere; }
tbody tr:nth-child(4n+3) { background: color-mix(in srgb, var(--panel-2) 45%, transparent); }
tbody tr.detail:nth-child(4n+3) { background: var(--bg); }

@media print {
  header.top { position: static; }
  .tabpanel { display: block !important; page-break-inside: avoid; }
  nav.tabs, .controls, button.ghost { display: none !important; }
  tr.detail, .hidden { display: table-row !important; }
  iframe.preview { height: 300px; }
  body { font-size: 11px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
"""

JS = """
(function () {
  'use strict';

  // ---- theme -------------------------------------------------------
  var root = document.documentElement;
  function currentTheme() {
    return root.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }
  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('grading-theme', next); } catch (e) {}
    });
  }

  // ---- fragment state ----------------------------------------------
  function readFragment() {
    var out = {};
    (location.hash || '').replace(/^#/, '').split('&').forEach(function (part) {
      var pair = part.split('=');
      if (pair[0]) { out[pair[0]] = decodeURIComponent(pair.slice(1).join('=')); }
    });
    return out;
  }
  function writeFragment(patch) {
    var state = readFragment();
    Object.keys(patch).forEach(function (key) {
      if (patch[key] === null) { delete state[key]; } else { state[key] = patch[key]; }
    });
    var text = Object.keys(state).map(function (key) {
      return key + '=' + encodeURIComponent(state[key]);
    }).join('&');
    history.replaceState(null, '', text ? '#' + text : location.pathname);
  }

  // ---- tabs --------------------------------------------------------
  // A panel does not need a tab button. Run detail is reached by clicking a
  // run in the list, so its panel exists with no button of its own; the tab
  // strip simply shows nothing selected while a run is open.
  function selectTab(name, quiet) {
    var panels = document.querySelectorAll('.tabpanel[data-tab="' + cssEscape(name) + '"]');
    if (!panels.length) { return false; }
    document.querySelectorAll('nav.tabs button[data-tab]').forEach(function (button) {
      button.setAttribute('aria-selected',
        button.getAttribute('data-tab') === name ? 'true' : 'false');
    });
    document.querySelectorAll('.tabpanel').forEach(function (panel) {
      panel.classList.toggle('active', panel.getAttribute('data-tab') === name);
    });
    if (!quiet) { writeFragment({ tab: name }); }
    window.scrollTo(0, 0);
    return true;
  }

  function cssEscape(value) {
    return String(value).replace(/["\\\\]/g, '\\\\$&');
  }
  document.querySelectorAll('nav.tabs button[data-tab]').forEach(function (button, index, all) {
    button.addEventListener('click', function () { selectTab(button.getAttribute('data-tab')); });
    button.addEventListener('keydown', function (event) {
      var step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!step) { return; }
      event.preventDefault();
      var next = all[(index + step + all.length) % all.length];
      next.focus();
      selectTab(next.getAttribute('data-tab'));
    });
  });

  // ---- sorting -----------------------------------------------------
  // Sorts values Python already computed. Nothing here calculates a score.

  // Strict: a value counts as numeric only if the WHOLE string is a number.
  // parseFloat is not strict — parseFloat('2026-07-30T15:48:05Z') is 2026, so
  // every timestamp in a column compared equal and the column never sorted.
  function asNumber(value) {
    if (value === null || value === '') { return null; }
    var n = Number(value);
    return isFinite(n) ? n : null;
  }

  function sortTable(table, index, dir) {
    var body = table.tBodies[0];
    var groups = [];
    Array.prototype.forEach.call(body.rows, function (row) {
      if (row.classList.contains('detail')) {
        if (groups.length) { groups[groups.length - 1].push(row); }
      } else { groups.push([row]); }
    });
    groups.sort(function (a, b) {
      var x = a[0].cells[index], y = b[0].cells[index];
      var xv = x ? x.getAttribute('data-sort') : null;
      var yv = y ? y.getAttribute('data-sort') : null;
      // Missing values sink to the bottom whichever way the column is sorted:
      // an unscored run is not "the worst", it is simply not a data point.
      var xMissing = xv === null || xv === '';
      var yMissing = yv === null || yv === '';
      if (xMissing && yMissing) { return 0; }
      if (xMissing) { return 1; }
      if (yMissing) { return -1; }
      var xn = asNumber(xv), yn = asNumber(yv);
      var cmp = (xn !== null && yn !== null)
        ? xn - yn
        : String(xv).localeCompare(String(yv));
      return dir === 'desc' ? -cmp : cmp;
    });
    groups.forEach(function (group) {
      group.forEach(function (row) { body.appendChild(row); });
    });
  }
  document.querySelectorAll('table[data-sortable]').forEach(function (table) {
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, index) {
      if (!th.classList.contains('sortable')) { return; }
      th.setAttribute('tabindex', '0');
      var activate = function () {
        var dir = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
        Array.prototype.forEach.call(table.tHead.rows[0].cells, function (other) {
          other.removeAttribute('data-dir');
        });
        th.setAttribute('data-dir', dir);
        sortTable(table, index, dir);
      };
      th.addEventListener('click', activate);
      th.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
      });
    });
  });

  // ---- filtering + search ------------------------------------------
  function applyFilters(scope) {
    var table = scope.querySelector('table[data-filterable]');
    if (!table) { return; }
    var active = [];
    scope.querySelectorAll('.chip[data-filter]').forEach(function (chip) {
      if (chip.getAttribute('aria-pressed') === 'true') {
        active.push(chip.getAttribute('data-filter'));
      }
    });
    var box = scope.querySelector('input[type="search"]');
    var term = box ? box.value.trim().toLowerCase() : '';
    var shown = 0, total = 0;
    Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
      if (row.classList.contains('detail')) { return; }
      total += 1;
      var flags = (row.getAttribute('data-flags') || '').split(' ');
      var okFlags = active.every(function (name) { return flags.indexOf(name) !== -1; });
      var haystack = (row.getAttribute('data-search') || '').toLowerCase();
      var okTerm = !term || haystack.indexOf(term) !== -1;
      var visible = okFlags && okTerm;
      row.classList.toggle('hidden', !visible);
      var detail = row.nextElementSibling;
      if (detail && detail.classList.contains('detail') && !visible) {
        detail.classList.add('hidden');
      }
      if (visible) { shown += 1; }
    });
    var count = scope.querySelector('.count');
    if (count) { count.textContent = 'showing ' + shown + ' of ' + total; }
  }
  document.querySelectorAll('[data-filterscope]').forEach(function (scope) {
    scope.querySelectorAll('.chip[data-filter]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var on = chip.getAttribute('aria-pressed') === 'true';
        chip.setAttribute('aria-pressed', on ? 'false' : 'true');
        applyFilters(scope);
      });
    });
    var box = scope.querySelector('input[type="search"]');
    if (box) {
      box.addEventListener('input', function () { applyFilters(scope); });
      box.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { box.value = ''; applyFilters(scope); }
      });
    }
    applyFilters(scope);
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === '/' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      var box = document.querySelector('input[type="search"]');
      if (box) { event.preventDefault(); box.focus(); }
    }
  });

  // ---- phase tabs inside a run panel -------------------------------
  // Scoped to their own container: the top-level tab strip and a run's phase
  // strip must never select each other's panels.
  document.querySelectorAll('[data-phasescope]').forEach(function (scope) {
    var buttons = scope.querySelectorAll('[data-phasetab]');
    function show(name) {
      buttons.forEach(function (button) {
        button.setAttribute('aria-pressed',
          button.getAttribute('data-phasetab') === name ? 'true' : 'false');
      });
      scope.querySelectorAll('[data-phasepanel]').forEach(function (panel) {
        panel.classList.toggle('hidden', panel.getAttribute('data-phasepanel') !== name);
      });
    }
    buttons.forEach(function (button, index) {
      button.addEventListener('click', function () {
        show(button.getAttribute('data-phasetab'));
      });
      button.addEventListener('keydown', function (event) {
        var step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (!step) { return; }
        event.preventDefault();
        var next = buttons[(index + step + buttons.length) % buttons.length];
        next.focus();
        show(next.getAttribute('data-phasetab'));
      });
    });
  });

  // Opening a row deep-link must also reveal the phase panel holding it.
  function revealPhaseOf(element) {
    var panel = element.closest ? element.closest('[data-phasepanel]') : null;
    if (!panel) { return; }
    var scope = panel.closest('[data-phasescope]');
    if (!scope) { return; }
    var name = panel.getAttribute('data-phasepanel');
    scope.querySelectorAll('[data-phasepanel]').forEach(function (other) {
      other.classList.toggle('hidden', other !== panel);
    });
    scope.querySelectorAll('[data-phasetab]').forEach(function (button) {
      button.setAttribute('aria-pressed',
        button.getAttribute('data-phasetab') === name ? 'true' : 'false');
    });
  }

  // ---- opening a run from the list ---------------------------------
  document.querySelectorAll('[data-open-run]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      writeFragment({ run: null, row: null });
      selectTab('run:' + link.getAttribute('data-open-run'));
    });
  });
  document.querySelectorAll('[data-back]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      writeFragment({ run: null, row: null });
      selectTab(link.getAttribute('data-back'));
    });
  });

  // ---- expandable rows ---------------------------------------------
  function expandRow(id, quiet) {
    var trigger = document.querySelector('[data-expand="' + id + '"]');
    var detail = document.getElementById('detail-' + id);
    if (!trigger || !detail) { return false; }
    revealPhaseOf(detail);
    var open = detail.classList.toggle('hidden');
    trigger.setAttribute('aria-expanded', open ? 'false' : 'true');
    if (!open && !quiet) { writeFragment({ row: id }); }
    return !open;
  }
  document.querySelectorAll('[data-expand]').forEach(function (trigger) {
    var id = trigger.getAttribute('data-expand');
    trigger.setAttribute('tabindex', '0');
    trigger.setAttribute('role', 'button');
    trigger.addEventListener('click', function () { expandRow(id); });
    trigger.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); expandRow(id); }
    });
  });

  // ---- preview / source toggles ------------------------------------
  document.querySelectorAll('[data-toggle-target]').forEach(function (button) {
    button.addEventListener('click', function () {
      var target = document.getElementById(button.getAttribute('data-toggle-target'));
      if (target) { target.classList.toggle('hidden'); }
    });
  });

  // ---- copy buttons ------------------------------------------------
  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var text = button.getAttribute('data-copy');
      var done = function () {
        var was = button.textContent; button.textContent = 'copied';
        setTimeout(function () { button.textContent = was; }, 1200);
      };
      if (navigator.clipboard) { navigator.clipboard.writeText(text).then(done, function () {}); }
    });
  });

  // ---- prompt version diff selection --------------------------------
  document.querySelectorAll('[data-diffscope]').forEach(function (scope) {
    var left = scope.querySelector('select[data-role="left"]');
    var right = scope.querySelector('select[data-role="right"]');
    if (!left || !right) { return; }
    function show() {
      scope.querySelectorAll('[data-diffpair]').forEach(function (panel) {
        var want = left.value + '::' + right.value;
        panel.classList.toggle('hidden', panel.getAttribute('data-diffpair') !== want);
      });
    }
    left.addEventListener('change', show);
    right.addEventListener('change', show);
    show();
  });

  // ---- restore state from the fragment ------------------------------
  var state = readFragment();
  if (state.run) { selectTab('run:' + state.run, true); }
  if (state.tab) { selectTab(state.tab, true); }
  if (state.stage) { selectTab(state.stage, true); }
  if (state.view) { selectTab(state.view, true); }
  if (state.row) {
    if (expandRow(state.row, true)) {
      var target = document.getElementById('detail-' + state.row);
      if (target && target.scrollIntoView) { target.scrollIntoView({ block: 'center' }); }
    }
  }
})();
"""
