'use strict';
/*
 * Small, comment- and string-aware CSS helpers shared by snapshot.cjs and
 * trim.cjs. No dependencies. Handles nested at-rules (@media, @supports,
 * @layer, @container); @keyframes / @font-face bodies are kept opaque.
 */

// Split a stylesheet into top-level items: { kind: 'rule'|'at'|'block-at', head, body, raw }
function split(css) {
  const items = [];
  let i = 0, start = 0;
  const n = css.length;
  while (i < n) {
    const c = css[i];
    if (c === '/' && css[i + 1] === '*') { const e = css.indexOf('*/', i + 2); i = e === -1 ? n : e + 2; continue; }
    if (c === '"' || c === "'") { i = skipString(css, i); continue; }
    if (c === ';' ) { // statement at-rule (@import, @charset, @layer a,b;)
      const raw = css.slice(start, i + 1).trim();
      if (raw) items.push({ kind: 'at', head: raw, body: null, raw });
      start = i + 1; i++; continue;
    }
    if (c === '{') {
      const end = matchBrace(css, i);
      const head = stripComments(css.slice(start, i)).trim();
      const body = css.slice(i + 1, end);
      const raw = head + '{' + body + '}';
      if (head) items.push({ kind: head.startsWith('@') ? 'block-at' : 'rule', head, body, raw });
      i = end + 1; start = i; continue;
    }
    i++;
  }
  return items;
}

function skipString(s, i) {
  const q = s[i];
  i++;
  while (i < s.length && s[i] !== q) { if (s[i] === '\\') i++; i++; }
  return i + 1;
}

function matchBrace(s, open) {
  let depth = 0;
  for (let i = open; i < s.length; i++) {
    const c = s[i];
    if (c === '/' && s[i + 1] === '*') { const e = s.indexOf('*/', i + 2); i = e === -1 ? s.length : e + 1; continue; }
    if (c === '"' || c === "'") { i = skipString(s, i) - 1; continue; }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return i; }
  }
  return s.length - 1;
}

function stripComments(s) { return s.replace(/\/\*[\s\S]*?\*\//g, ''); }

const NESTED = /^@(media|supports|layer|container|document)\b/i;

// Split a selector list on top-level commas (not inside :is()/:not()/[...]).
function selectors(head) {
  const out = []; let depth = 0, cur = '';
  for (const ch of head) {
    if (ch === '(' || ch === '[') depth++;
    if (ch === ')' || ch === ']') depth--;
    if (ch === ',' && depth === 0) { out.push(cur.trim()); cur = ''; } else cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/*
 * Rewrite a stylesheet item by item. fn(item) returns a replacement raw string,
 * '' to drop it, or undefined to keep it. Nested at-rules are recursed into.
 */
function map(css, fn) {
  return split(css).map(it => {
    if (it.kind === 'block-at' && NESTED.test(it.head)) {
      const inner = map(it.body, fn).trim();
      return inner ? `${it.head}{${inner}}` : '';
    }
    const r = fn(it);
    return r === undefined ? it.raw : r;
  }).filter(Boolean).join('\n');
}

// Drop exact duplicate items, keeping the LAST occurrence (cascade order kept).
function dedupe(css) {
  const items = split(css);
  const lastIndex = new Map();
  items.forEach((it, i) => lastIndex.set(norm(it.raw), i));
  return items.filter((it, i) => lastIndex.get(norm(it.raw)) === i).map(it => it.raw).join('\n');
}

function norm(s) { return stripComments(s).replace(/\s+/g, ' ').trim(); }

/*
 * Remove style rules whose every selector names a class that is not used in
 * the markup. `used` is a Set of class names; `keep` a RegExp of class names to
 * keep regardless (state classes toggled at runtime).
 */
function pruneUnused(css, used, keep) {
  let removed = 0;
  const out = map(css, it => {
    if (it.kind !== 'rule') return undefined;
    const sels = selectors(it.head);
    const alive = sels.filter(sel => {
      const classes = [...sel.replace(/\[[^\]]*\]/g, '').matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map(m => m[1]);
      return classes.every(c => used.has(c) || keep.test(c));
    });
    if (!alive.length) { removed++; return ''; }
    if (alive.length < sels.length) return `${alive.join(',')}{${it.body}}`;
    return undefined;
  });
  return { css: out, removed };
}

function minify(css) {
  return stripComments(css)
    .replace(/\s+/g, ' ')
    .replace(/\s*([{};,>])\s*/g, '$1')
    .replace(/:\s+/g, ':')
    .replace(/;}/g, '}')
    .trim();
}

// Unbalanced braces or comments -- used as a sanity check before writing.
function balanced(css) {
  const opens = (css.match(/\/\*/g) || []).length, closes = (css.match(/\*\//g) || []).length;
  if (opens !== closes) return `unbalanced comments (${opens} /* vs ${closes} */)`;
  let depth = 0;
  const s = stripComments(css).replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, '""');
  for (const ch of s) { if (ch === '{') depth++; else if (ch === '}') { depth--; if (depth < 0) return 'unbalanced braces (extra })'; } }
  return depth === 0 ? null : `unbalanced braces (${depth} unclosed {)`;
}

function classesIn(html) {
  const used = new Set();
  for (const m of html.matchAll(/\bclass="([^"]*)"/g)) for (const c of m[1].split(/\s+/)) if (c) used.add(c);
  return used;
}

module.exports = { split, map, dedupe, pruneUnused, minify, balanced, selectors, classesIn };
