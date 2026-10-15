"""app/api/run_figma_export.py — POST /api/runs/{id}/figma-export

Renders prototype.html in headless Chromium (Playwright), runs the
production-grade SCRAPE_FN DOM extraction script (MIT — adapted from
github.com/flukelaster/claude-design-x-figma), and returns the raw
Intermediate Representation (IRNode tree) as JSON.

The Figma plugin (code.js) receives this IR and builds real Figma frames
using the companion mapper — auto-layout, fills, text, SVG, gradients,
shadows, and images are all handled there.

Architecture:
  Backend  → Playwright render + SCRAPE_FN → { screens, viewport, tokens }
  Plugin   → mapper (buildTree)            → real Figma nodes

SCRAPE_FN extracts:
  - Complete DOM tree with computed styles (getComputedStyle for every prop)
  - Bounding rects (getBoundingClientRect for every element)
  - CSS custom properties / design tokens
  - Pseudo-elements (::before / ::after)
  - SVG outerHTML for vector fidelity
  - Form control values / placeholders
  - Canvas / video frames as data-URIs

Security:
  Two-layer IDOR identical to run_files.py.
  HTML served as file:// URI — never proxied to external services.

Viewport: 1440 × 900 (matches Figma frames the plugin creates).

Windows / uvicorn SelectorEventLoop:
  Playwright runs in a ThreadPoolExecutor thread via asyncio.run() which
  creates its own isolated event loop — a ProactorEventLoop on Windows
  (because of WindowsProactorEventLoopPolicy set in main.py). Completely
  bypasses uvicorn's SelectorEventLoop.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import math
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.agents.sandbox import RunSandbox, run_dir_expired
from app.api.run_files import (
    _resolve_chain_root_or_404,
    _resolve_owned_run,
    _validate_ref,
)
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.run_figma_export")

router = APIRouter(prefix="/api/runs", tags=["run-figma-export"])

_VIEWPORT_W = 1440
_VIEWPORT_H = 900
_GOTO_TIMEOUT_MS = 20_000

# ── SCRAPE_FN ─────────────────────────────────────────────────────────────────
# Production-grade in-page DOM → IRNode extractor.
# MIT License — adapted from github.com/flukelaster/claude-design-x-figma
# (cli/scrape-injected.ts). Self-contained: no imports, no outer-scope closures.
# Returns: { screens: IRNode[], viewport: {w,h}, tokens: TokenSet|null }
#
# Key capabilities vs our previous custom extractor:
#   • Captures ALL screens (multi-screen SPA: activates each [data-page] child)
#   • Resolves CSS variables via getComputedStyle (not just inline styles)
#   • Extracts ::before/::after pseudo-elements
#   • Handles SVG (outerHTML), canvas/video (toDataURL), form controls
#   • Extracts CSS custom property token sets for Figma Variables
#   • Correctly handles page-relative vs viewport-relative coordinates
_SCRAPE_FN = r"""
(() => {
  const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','META','LINK','HEAD','TITLE']);
  const TEXT_NODE = 3, ELEMENT_NODE = 1;

  function px(v) {
    if (!v) return undefined;
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : undefined;
  }

  function pickComputed(el) {
    const c = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      display: c.display,
      flexDirection: c.flexDirection,
      justifyContent: c.justifyContent,
      alignItems: c.alignItems,
      gap: px(c.rowGap || c.columnGap || c.gap),
      paddingTop: px(c.paddingTop), paddingRight: px(c.paddingRight),
      paddingBottom: px(c.paddingBottom), paddingLeft: px(c.paddingLeft),
      marginTop: px(c.marginTop), marginRight: px(c.marginRight),
      marginBottom: px(c.marginBottom), marginLeft: px(c.marginLeft),
      width: px(c.width), height: px(c.height),
      backgroundColor: c.backgroundColor,
      backgroundImage: c.backgroundImage && c.backgroundImage !== 'none' ? c.backgroundImage : undefined,
      backdropFilter: (c.backdropFilter && c.backdropFilter !== 'none') ? c.backdropFilter
        : ((c.webkitBackdropFilter && c.webkitBackdropFilter !== 'none') ? c.webkitBackdropFilter : undefined),
      color: c.color,
      fontSize: px(c.fontSize),
      fontWeight: parseInt(c.fontWeight, 10) || undefined,
      fontFamily: c.fontFamily,
      fontStyle: c.fontStyle,
      lineHeight: px(c.lineHeight),
      letterSpacing: px(c.letterSpacing),
      textAlign: c.textAlign,
      borderTopLeftRadius: px(c.borderTopLeftRadius),
      borderTopRightRadius: px(c.borderTopRightRadius),
      borderBottomLeftRadius: px(c.borderBottomLeftRadius),
      borderBottomRightRadius: px(c.borderBottomRightRadius),
      borderTopWidth: px(c.borderTopWidth),
      borderRightWidth: px(c.borderRightWidth),
      borderBottomWidth: px(c.borderBottomWidth),
      borderLeftWidth: px(c.borderLeftWidth),
      borderColor: c.borderTopColor,
      borderRightColor: c.borderRightColor,
      borderBottomColor: c.borderBottomColor,
      borderLeftColor: c.borderLeftColor,
      borderTopStyle: c.borderTopStyle,
      borderRightStyle: c.borderRightStyle,
      borderBottomStyle: c.borderBottomStyle,
      borderLeftStyle: c.borderLeftStyle,
      boxShadow: c.boxShadow,
      opacity: parseFloat(c.opacity),
      position: c.position,
      top: px(c.top), right: px(c.right), bottom: px(c.bottom), left: px(c.left),
      zIndex: c.zIndex && c.zIndex !== 'auto' ? parseInt(c.zIndex, 10) : undefined,
      overflow: c.overflow,
      transform: c.transform && c.transform !== 'none' ? c.transform : undefined,
      textTransform: c.textTransform,
      textDecorationLine: c.textDecorationLine && c.textDecorationLine !== 'none' ? c.textDecorationLine : undefined,
      textDecorationStyle: c.textDecorationStyle,
      textDecorationColor: c.textDecorationColor,
      filter: c.filter && c.filter !== 'none' ? c.filter : undefined,
      mixBlendMode: c.mixBlendMode && c.mixBlendMode !== 'normal' ? c.mixBlendMode : undefined,
      objectFit: c.objectFit,
      objectPosition: c.objectPosition,
      backgroundSize: c.backgroundSize,
      backgroundPosition: c.backgroundPosition,
      backgroundRepeat: c.backgroundRepeat,
      clipPath: c.clipPath && c.clipPath !== 'none' ? c.clipPath : undefined,
      textOverflow: c.textOverflow,
      whiteSpace: c.whiteSpace,
      listStyleType: c.listStyleType,
      verticalAlign: c.verticalAlign,
      rectX: r.x, rectY: r.y, rectW: r.width, rectH: r.height,
    };
  }

  function attrMap(el) {
    const out = {};
    for (const a of el.attributes) {
      if (a.name.startsWith('data-om')) continue;
      out[a.name] = a.value;
    }
    return out;
  }

  function substituteKeycaps(s) {
    if (!s) return s;
    const CIRCLED = ['\u24ea','\u2460','\u2461','\u2462','\u2463','\u2464','\u2465','\u2466','\u2467','\u2468'];
    return s.replace(/([0-9])\uFE0F\u20E3/g, (_, d) => CIRCLED[+d]);
  }

  function isInvisible(el, cs) {
    if (cs.display === 'none' || cs.visibility === 'hidden') return true;
    if (parseFloat(cs.opacity) === 0) return true;
    return false;
  }

  function listMarker(el, type) {
    if (!type || type === 'none') return '';
    if (type === 'disc') return '\u2022 ';
    if (type === 'circle') return '\u25e6 ';
    if (type === 'square') return '\u25aa ';
    if (type === 'decimal') {
      let idx = 1;
      let prev = el.previousElementSibling;
      while (prev) { if (prev.tagName === 'LI') idx++; prev = prev.previousElementSibling; }
      return idx + '. ';
    }
    return '';
  }

  function getPseudoIR(el, pseudo) {
    let cs;
    try { cs = window.getComputedStyle(el, pseudo); } catch { return null; }
    if (!cs) return null;
    const display = cs.display;
    if (!display || display === 'none') return null;
    const rawContent = cs.content;
    if (!rawContent || rawContent === 'none' || rawContent === 'normal') return null;
    let text = '';
    const quoted = rawContent.match(/^["'](.*)["']$/);
    if (quoted) text = substituteKeycaps(quoted[1]);
    const w = px(cs.width) ?? 0;
    const h = px(cs.height) ?? 0;
    const hasText = text.length > 0;
    const hasBox = (w > 0 || h > 0) && (
      cs.backgroundColor !== 'rgba(0, 0, 0, 0)' ||
      (cs.backgroundImage && cs.backgroundImage !== 'none') ||
      px(cs.borderTopWidth) || px(cs.borderRightWidth) ||
      px(cs.borderBottomWidth) || px(cs.borderLeftWidth)
    );
    if (!hasText && !hasBox) return null;
    const r = el.getBoundingClientRect();
    let rectX = r.x, rectY = r.y;
    const top = px(cs.top), left = px(cs.left), right = px(cs.right), bottom = px(cs.bottom);
    if (cs.position === 'absolute' || cs.position === 'fixed') {
      if (left !== undefined) rectX = r.x + left;
      else if (right !== undefined) rectX = r.x + r.width - right - w;
      if (top !== undefined) rectY = r.y + top;
      else if (bottom !== undefined) rectY = r.y + r.height - bottom - h;
    }
    const computed = {
      display: display === 'inline' ? 'inline-block' : display,
      width: w, height: h,
      backgroundColor: cs.backgroundColor,
      backgroundImage: cs.backgroundImage && cs.backgroundImage !== 'none' ? cs.backgroundImage : undefined,
      color: cs.color,
      fontSize: px(cs.fontSize),
      fontWeight: parseInt(cs.fontWeight, 10) || undefined,
      fontFamily: cs.fontFamily,
      fontStyle: cs.fontStyle,
      lineHeight: px(cs.lineHeight),
      letterSpacing: px(cs.letterSpacing),
      textAlign: cs.textAlign,
      borderTopLeftRadius: px(cs.borderTopLeftRadius),
      borderTopRightRadius: px(cs.borderTopRightRadius),
      borderBottomLeftRadius: px(cs.borderBottomLeftRadius),
      borderBottomRightRadius: px(cs.borderBottomRightRadius),
      borderTopWidth: px(cs.borderTopWidth),
      borderRightWidth: px(cs.borderRightWidth),
      borderBottomWidth: px(cs.borderBottomWidth),
      borderLeftWidth: px(cs.borderLeftWidth),
      borderColor: cs.borderTopColor,
      boxShadow: cs.boxShadow,
      opacity: parseFloat(cs.opacity),
      position: cs.position === 'static' ? undefined : cs.position,
      transform: cs.transform && cs.transform !== 'none' ? cs.transform : undefined,
      zIndex: cs.zIndex && cs.zIndex !== 'auto' ? parseInt(cs.zIndex, 10) : undefined,
      rectX, rectY, rectW: w, rectH: h,
    };
    if (hasText && !hasBox) return { tag: '#text', text, attrs: {}, classNames: [], inlineStyle: {}, style: {}, computed, children: [] };
    const children = hasText
      ? [{ tag: '#text', text, attrs: {}, classNames: [], inlineStyle: {}, style: {}, computed, children: [] }]
      : [];
    return { tag: 'div', text: hasText && children.length === 1 ? text : undefined,
      attrs: { 'data-pseudo': pseudo.slice(2) }, classNames: [], inlineStyle: {}, style: {}, computed, children };
  }

  function isInlineTextContainer(el) {
    const INLINE = new Set(['SPAN','STRONG','EM','A','B','I','SMALL','SUP','SUB','MARK','U','CODE']);
    for (const c of el.childNodes) {
      if (c.nodeType === TEXT_NODE) continue;
      if (c.nodeType !== ELEMENT_NODE) return false;
      if (!INLINE.has(c.tagName)) return false;
      if (!isInlineTextContainer(c)) return false;
    }
    return true;
  }

  function walk(el) {
    if (el.nodeType === TEXT_NODE) {
      const parentEl = el.parentElement;
      const pws = parentEl ? window.getComputedStyle(parentEl).whiteSpace : 'normal';
      const preserveAll = pws === 'pre' || pws === 'pre-wrap' || pws === 'break-spaces';
      const preserveLine = pws === 'pre-line';
      let t;
      if (preserveAll) t = (el.nodeValue || '');
      else if (preserveLine) t = (el.nodeValue || '').replace(/[ \t]+/g, ' ');
      else t = (el.nodeValue || '').replace(/\s+/g, ' ');
      t = substituteKeycaps(t);
      if (!preserveAll && !t.trim()) return null;
      let rect = null;
      try {
        const range = document.createRange();
        range.selectNodeContents(el);
        const r = range.getBoundingClientRect();
        if (r && (r.width || r.height)) rect = r;
      } catch {}
      const parent = el.parentElement;
      const pcs = parent ? window.getComputedStyle(parent) : null;
      const computed = rect ? {
        rectX: rect.x, rectY: rect.y, rectW: rect.width, rectH: rect.height,
        color: pcs ? pcs.color : undefined,
        fontSize: pcs ? parseFloat(pcs.fontSize) : undefined,
        fontWeight: pcs ? (parseInt(pcs.fontWeight, 10) || undefined) : undefined,
        fontFamily: pcs ? pcs.fontFamily : undefined,
        fontStyle: pcs ? pcs.fontStyle : undefined,
        lineHeight: pcs ? parseFloat(pcs.lineHeight) : undefined,
        letterSpacing: pcs ? parseFloat(pcs.letterSpacing) : undefined,
        textAlign: pcs ? pcs.textAlign : undefined,
        textTransform: pcs ? pcs.textTransform : undefined,
        textDecorationLine: pcs && pcs.textDecorationLine && pcs.textDecorationLine !== 'none' ? pcs.textDecorationLine : undefined,
      } : undefined;
      return { tag: '#text', text: t, attrs: {}, classNames: [], inlineStyle: {}, style: {}, computed, children: [] };
    }
    if (el.nodeType !== ELEMENT_NODE) return null;
    const tag = el.tagName.toLowerCase();
    if (SKIP.has(el.tagName)) return null;
    if (tag === 'br') return { tag: '#text', text: '\n', attrs: {}, classNames: [], inlineStyle: {}, style: {}, children: [] };
    const cs = window.getComputedStyle(el);
    if (isInvisible(el, cs)) return null;
    const computed = pickComputed(el);
    if ((!computed.rectW || !computed.rectH) && !el.childNodes.length) return null;

    if (tag === 'svg') {
      return { tag: 'svg', text: undefined,
        attrs: { __svg: el.outerHTML, ...attrMap(el) },
        classNames: [], inlineStyle: {}, style: {}, computed, children: [] };
    }

    if (tag === 'canvas' || tag === 'video') {
      let dataUrl = null;
      try {
        if (tag === 'canvas') { dataUrl = el.toDataURL('image/png'); }
        else {
          const c = document.createElement('canvas');
          c.width = el.videoWidth || el.clientWidth || 1;
          c.height = el.videoHeight || el.clientHeight || 1;
          const ctx = c.getContext('2d');
          if (ctx) { ctx.drawImage(el, 0, 0, c.width, c.height); dataUrl = c.toDataURL('image/png'); }
        }
      } catch {}
      if (dataUrl) return { tag: 'img', text: undefined,
        attrs: { src: dataUrl, alt: tag, ...attrMap(el) },
        classNames: [], inlineStyle: {}, style: {}, computed, children: [] };
    }

    const children = [];
    const before = getPseudoIR(el, '::before');
    if (before) children.push(before);

    const isContentEditable = el.isContentEditable || el.getAttribute('contenteditable') === 'true';
    const role = el.getAttribute('role');
    const isCustomInput = isContentEditable || role === 'textbox' || role === 'searchbox' || role === 'combobox';
    const ariaPlaceholder = el.getAttribute('aria-placeholder') || el.getAttribute('data-placeholder') || el.getAttribute('placeholder');
    const isFormControl = tag === 'input' || tag === 'textarea' || tag === 'select';
    const inputType = (tag === 'input' ? (el.getAttribute('type') || 'text') : '').toLowerCase();
    const isCheckable = tag === 'input' && (inputType === 'checkbox' || inputType === 'radio');
    const isChecked = isCheckable && !!el.checked;
    const shouldInject = (isFormControl && !isCheckable) || ((isCustomInput || ariaPlaceholder) && !((el.textContent || '').trim()));
    if (shouldInject) {
      let displayText = '', isPlaceholder = false;
      if (tag === 'select') {
        const opt = el.options && el.options[el.selectedIndex];
        displayText = opt ? (opt.textContent || '').trim() : '';
        if (displayText) displayText += '  \u25be';
      } else if (isFormControl) {
        const value = (el.value || '').trim();
        if (value) displayText = value;
        else { displayText = (el.getAttribute('placeholder') || ariaPlaceholder || '').trim(); isPlaceholder = true; }
      } else {
        displayText = (ariaPlaceholder || '').trim(); isPlaceholder = true;
      }
      displayText = substituteKeycaps(displayText);
      if (displayText) {
        const r3 = el.getBoundingClientRect();
        let phColor;
        if (isPlaceholder) {
          try { phColor = window.getComputedStyle(el, '::placeholder').color; } catch {}
          if (phColor) computed.color = phColor;
        }
        const padL = parseFloat(cs.paddingLeft) || 0;
        const padT = parseFloat(cs.paddingTop) || 0;
        const padR = parseFloat(cs.paddingRight) || 0;
        const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) || 16;
        children.push({ tag: '#text', text: displayText, attrs: {}, classNames: [], inlineStyle: {}, style: {},
          computed: {
            rectX: r3.x + padL, rectY: r3.y + padT + Math.max(0, (r3.height - 2*padT - lh) / 2),
            rectW: Math.max(1, r3.width - padL - padR), rectH: lh,
            color: phColor || cs.color, fontSize: parseFloat(cs.fontSize) || undefined,
            fontWeight: parseInt(cs.fontWeight, 10) || undefined, fontFamily: cs.fontFamily,
            fontStyle: cs.fontStyle, lineHeight: parseFloat(cs.lineHeight) || undefined,
            letterSpacing: parseFloat(cs.letterSpacing) || undefined, textAlign: cs.textAlign,
          }, children: [] });
      }
    }
    if (isCheckable && isChecked) {
      const r4 = el.getBoundingClientRect();
      const glyph = inputType === 'checkbox' ? '\u2713' : '\u25cf';
      const fs = Math.max(8, Math.min(r4.height, r4.width) * 0.7);
      children.push({ tag: '#text', text: glyph, attrs: {}, classNames: [], inlineStyle: {}, style: {},
        computed: { rectX: r4.x + (r4.width - fs*0.6)/2, rectY: r4.y + (r4.height - fs)/2,
          rectW: fs, rectH: fs, color: inputType === 'checkbox' ? '#FFFFFF' : (cs.color || '#1F2937'),
          fontSize: fs, fontWeight: 700, fontFamily: cs.fontFamily, fontStyle: 'normal', textAlign: 'center' }, children: [] });
    }
    if (tag === 'li' && cs.display === 'list-item') {
      const markerText = listMarker(el, cs.listStyleType);
      if (markerText) {
        const r2 = el.getBoundingClientRect();
        children.push({ tag: '#text', text: markerText, attrs: {}, classNames: [], inlineStyle: {}, style: {},
          computed: { rectX: r2.x, rectY: r2.y, rectW: 24, rectH: parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) || 16,
            color: cs.color, fontSize: parseFloat(cs.fontSize), fontWeight: parseInt(cs.fontWeight, 10) || undefined,
            fontFamily: cs.fontFamily, fontStyle: cs.fontStyle, lineHeight: parseFloat(cs.lineHeight) }, children: [] });
      }
    }
    for (const c of el.childNodes) { const ir = walk(c); if (ir) children.push(ir); }
    const after = getPseudoIR(el, '::after');
    if (after) children.push(after);
    let text;
    if (children.length === 1 && children[0].tag === '#text') text = children[0].text;
    return { tag, text, attrs: attrMap(el), classNames: (el.className && typeof el.className === 'string') ? el.className.split(/\s+/).filter(Boolean) : [], inlineStyle: {}, style: {}, computed, children };
  }

  function classifyMode(selectorText, mediaText) {
    if (mediaText && /prefers-color-scheme\s*:\s*dark/i.test(mediaText)) return 'Dark';
    if (mediaText && /prefers-color-scheme\s*:\s*light/i.test(mediaText)) return 'Light';
    if (!selectorText) return null;
    const s = selectorText.toLowerCase();
    if (/(^|[^a-z0-9_-])\.dark(\b|[^a-z0-9_-])/.test(s)) return 'Dark';
    if (/\[data-theme[^\]]*=[^\]]*['"]?dark['"]?\]/.test(s)) return 'Dark';
    if (/(^|[^a-z0-9_-])\.light(\b|[^a-z0-9_-])/.test(s)) return 'Light';
    if (s === ':root' || s === 'html' || s === 'body' || s === '*') return 'Light';
    return null;
  }
  function classifyType(value) {
    const v = (value || '').trim();
    if (!v || /^var\(/.test(v)) return null;
    if (/^#[0-9a-f]{3,8}$/i.test(v)) return 'COLOR';
    if (/^(rgb|rgba|hsl|hsla|hwb|oklch|oklab|lab|lch|color)\s*\(/i.test(v)) return 'COLOR';
    if (/^-?\d*\.?\d+(px|rem|em|%)?$/i.test(v)) return 'FLOAT';
    return 'STRING';
  }
  function collectStyleRules(rules, mediaText, out) {
    if (!rules) return;
    for (let i = 0; i < rules.length; i++) {
      const r = rules[i];
      if (!r) continue;
      if (r.type === 1 && r.style) out.push({ selectorText: r.selectorText, style: r.style, mediaText });
      else if (r.type === 4 && r.cssRules) collectStyleRules(r.cssRules, (r.media && r.media.mediaText) ? r.media.mediaText : mediaText, out);
      else if (r.cssRules) collectStyleRules(r.cssRules, mediaText, out);
    }
  }
  function extractTokens() {
    const out = { modes: ['Light'], vars: [] };
    const byName = new Map();
    const collected = [];
    for (const sheet of Array.from(document.styleSheets)) {
      let rules; try { rules = sheet.cssRules; } catch { continue; }
      if (!rules) continue;
      collectStyleRules(rules, undefined, collected);
    }
    for (const ctx of collected) {
      const mode = classifyMode(ctx.selectorText, ctx.mediaText);
      if (!mode) continue;
      if (!out.modes.includes(mode)) out.modes.push(mode);
      const style = ctx.style;
      for (let i = 0; i < style.length; i++) {
        const prop = style[i];
        if (!prop || !prop.startsWith('--')) continue;
        const value = style.getPropertyValue(prop).trim();
        if (!value) continue;
        let entry = byName.get(prop);
        if (!entry) { entry = { name: prop, type: 'STRING', values: {} }; byName.set(prop, entry); }
        entry.values[mode] = value;
      }
    }
    try {
      const rootCs = window.getComputedStyle(document.documentElement);
      for (const entry of byName.values()) {
        if (entry.values['Light']) continue;
        const v = rootCs.getPropertyValue(entry.name).trim();
        if (v) entry.values['Light'] = v;
      }
    } catch {}
    for (const entry of byName.values()) {
      let chosen = null;
      for (const mode of out.modes) { const v = entry.values[mode]; if (!v) continue; const t = classifyType(v); if (t) { chosen = t; break; } }
      entry.type = chosen || 'STRING';
      out.vars.push(entry);
    }
    return out;
  }

  const rootEl = document.getElementById('root');
  const root = (rootEl && rootEl.children.length > 0) ? rootEl : document.body;
  const viewportW = window.innerWidth;
  const childRects = [];
  for (const child of root.children) childRects.push(child.getBoundingClientRect());
  const isMultiScreen = childRects.length > 1 && childRects.every(r => Math.abs(r.y) < 50 && r.width >= viewportW * 0.8);
  const screens = [];
  if (isMultiScreen || childRects.length <= 1) {
    for (const child of root.children) { const ir = walk(child); if (ir) screens.push(ir); }
  } else {
    const ir = walk(root);
    if (ir) {
      const bodyCs = window.getComputedStyle(document.body);
      const htmlCs = window.getComputedStyle(document.documentElement);
      const isOpaque = c => c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent';
      const isImg = s => s && s !== 'none';
      ir.computed = ir.computed || {};
      if (!isOpaque(ir.computed.backgroundColor)) {
        if (isOpaque(bodyCs.backgroundColor)) ir.computed.backgroundColor = bodyCs.backgroundColor;
        else if (isOpaque(htmlCs.backgroundColor)) ir.computed.backgroundColor = htmlCs.backgroundColor;
      }
      if (!isImg(ir.computed.backgroundImage)) {
        if (isImg(bodyCs.backgroundImage)) {
          ir.computed.backgroundImage = bodyCs.backgroundImage;
          if (bodyCs.backgroundSize) ir.computed.backgroundSize = bodyCs.backgroundSize;
          if (bodyCs.backgroundPosition) ir.computed.backgroundPosition = bodyCs.backgroundPosition;
          if (bodyCs.backgroundRepeat) ir.computed.backgroundRepeat = bodyCs.backgroundRepeat;
        }
      }
      const bodyRect = document.body.getBoundingClientRect();
      const htmlRect = document.documentElement.getBoundingClientRect();
      const fullW = Math.max(ir.computed.rectW || 0, bodyRect.width, htmlRect.width, window.innerWidth);
      const fullH = Math.max(ir.computed.rectH || 0, bodyRect.height, htmlRect.height);
      ir.computed.rectW = fullW; ir.computed.rectH = fullH;
      ir.computed.width = fullW; ir.computed.height = fullH;
      screens.push(ir);
    }
  }

  let tokens = null;
  try { tokens = extractTokens(); } catch {}
  return { screens, viewport: { w: window.innerWidth, h: window.innerHeight }, tokens };
})()
"""


async def _run_playwright_extraction(html_uri: str) -> dict:
    """Run SCRAPE_FN in a dedicated thread with its own event loop.

    asyncio.run() creates a brand-new event loop — on Windows this is a
    ProactorEventLoop (WindowsProactorEventLoopPolicy set in main.py), which
    supports subprocesses. Completely isolated from uvicorn's SelectorEventLoop.
    """
    import asyncio
    import concurrent.futures

    async def _extract() -> dict:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(args=["--no-sandbox"])
            except Exception as exc:
                raise RuntimeError(f"Chromium launch failed: {exc}") from exc
            try:
                context = await browser.new_context(
                    viewport={"width": _VIEWPORT_W, "height": _VIEWPORT_H},
                    bypass_csp=True,
                    device_scale_factor=2,  # retina — sharper screenshots
                )
                page = await context.new_page()
                await page.goto(
                    html_uri, wait_until="networkidle", timeout=_GOTO_TIMEOUT_MS
                )
                # Give JS-rendered charts, animations and lazy images extra time to settle.
                await page.wait_for_timeout(1500)
                # Additionally wait until no network requests are in-flight
                # (covers lazy-loaded images / deferred scripts).
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                # ── Multi-screen discovery ─────────────────────────────────────
                # First try: find [data-page] sections — each is a distinct screen.
                # Second try: discover nav links (sidebar / tab bar) and capture
                #   the view after clicking each one.
                # Third try: fall back to SCRAPE_FN on the full page (single screen).

                all_screens: list[dict] = []

                # Collect nav links: anchors or buttons that switch the visible section.
                nav_links: list[str] = await page.evaluate("""
                (() => {
                    // Priority 1: elements that target a data-page section
                    const byDataPage = Array.from(
                        document.querySelectorAll('[data-page],[data-target],[href^="#"]')
                    );
                    // Priority 2: nav / sidebar link elements
                    const byNav = Array.from(
                        document.querySelectorAll(
                            'nav a, nav button, aside a, aside button, ' +
                            '.nav-item, .sidebar-item, .menu-item, .tab, [role="tab"], ' +
                            '[role="menuitem"], [role="option"]'
                        )
                    );
                    const candidates = byDataPage.length > 1 ? byDataPage : byNav;
                    const seen = new Set();
                    return candidates
                        .filter(el => {
                            const text = (el.textContent || '').trim();
                            if (!text || seen.has(text)) return false;
                            seen.add(text);
                            return true;
                        })
                        .map(el => el.textContent.trim())
                        .slice(0, 12);  // cap at 12 screens
                })()
                """)

                if len(nav_links) > 1:
                    # Click-through capture: click each nav link, settle, take screenshot,
                    # scrape IR. Deduplication uses a hash of the screenshot pixels —
                    # this is the only reliable signal that the view actually changed.
                    # The IR structure (child count, text) stays the same across nav
                    # clicks because the sidebar/header are always present.

                    seen_hashes: set[str] = set()

                    for label in nav_links:
                        try:
                            clicked = await page.evaluate(f"""
                            (() => {{
                                const label = {repr(label)};
                                const all = Array.from(document.querySelectorAll(
                                    'nav a, nav button, aside a, aside button, ' +
                                    '.nav-item, .sidebar-item, .menu-item, .tab, ' +
                                    '[role="tab"], [role="menuitem"], [role="option"], ' +
                                    '[data-page], [data-target], [href^="#"]'
                                ));
                                const el = all.find(e => (e.textContent || '').trim() === label);
                                if (el) {{ el.click(); return true; }}
                                return false;
                            }})()
                            """)
                            if not clicked:
                                continue

                            await page.wait_for_timeout(500)

                            # Screenshot — deduplication key + quality backstop
                            try:
                                screenshot_bytes = await page.screenshot(
                                    type="png",
                                    full_page=False,
                                    scale="css",
                                )
                                screenshot_b64 = (
                                    "data:image/png;base64,"
                                    + base64.b64encode(screenshot_bytes).decode()
                                )
                                # Dedup key for identical screenshots, not a security
                                # boundary — MD5 is fine here (bandit B324).
                                pixel_hash = hashlib.md5(
                                    screenshot_bytes, usedforsecurity=False
                                ).hexdigest()
                            except Exception:
                                screenshot_b64 = None
                                pixel_hash = label

                            if pixel_hash in seen_hashes:
                                continue
                            seen_hashes.add(pixel_hash)

                            screen_data = await page.evaluate(_SCRAPE_FN)
                            if not screen_data or not screen_data.get("screens"):
                                continue
                            first_screen = screen_data["screens"][0]
                            first_screen["_nav_label"] = label
                            if screenshot_b64:
                                first_screen["_screenshot"] = screenshot_b64
                            all_screens.append(first_screen)
                        except Exception:
                            pass

                if not all_screens:
                    # No multi-screen nav found — single full-page capture
                    try:
                        screenshot_bytes = await page.screenshot(
                            type="png", full_page=False, scale="css"
                        )
                        screenshot_b64 = (
                            "data:image/png;base64,"
                            + base64.b64encode(screenshot_bytes).decode()
                        )
                    except Exception:
                        screenshot_b64 = None
                    result = await page.evaluate(_SCRAPE_FN)
                    if result and result.get("screens"):
                        all_screens = result["screens"]
                        if screenshot_b64 and all_screens:
                            all_screens[0]["_screenshot"] = screenshot_b64
                    vp = (
                        result.get("viewport", {"w": _VIEWPORT_W, "h": _VIEWPORT_H})
                        if result
                        else {"w": _VIEWPORT_W, "h": _VIEWPORT_H}
                    )
                    tokens = result.get("tokens") if result else None
                    return {"screens": all_screens, "viewport": vp, "tokens": tokens}

                # Deduplicate screens that ended up looking identical (same tag + same number of children)
                # Use first-screen viewport / tokens
                first_result = await page.evaluate("""
                (() => ({ viewport: { w: window.innerWidth, h: window.innerHeight }, tokens: null }))()
                """)
                return {
                    "screens": all_screens,
                    "viewport": first_result.get(
                        "viewport", {"w": _VIEWPORT_W, "h": _VIEWPORT_H}
                    ),
                    "tokens": first_result.get("tokens"),
                }
            finally:
                await browser.close()

    def _run_in_thread() -> dict:
        return asyncio.run(_extract())

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        result = await loop.run_in_executor(pool, _run_in_thread)
    return result


def _sanitize_floats(obj: object) -> object:
    """Recursively replace NaN/Infinity floats with None.

    JavaScript's parseFloat("normal") → NaN, parseFloat("auto") → NaN, etc.
    Python's json.dumps raises ValueError on these — replace with null so
    the JSON is always valid. The plugin treats None/null as "not set".
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


@router.post("/{run_id}/figma-export")
async def figma_export(
    run_id: str,
    ref: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Render prototype.html in Chromium and return the IRNode tree as JSON.

    The Figma plugin receives this IR and calls buildTree() to create real
    Figma frames with auto-layout, fills, text, SVG, gradients, and images.

    Falls back to 503 when Playwright/Chromium is unavailable so the frontend
    degrades gracefully to the client-side DOM-walk export.

    ISS-974 — ``ref`` (a version tag, validated by ``_validate_ref``) renders that
    version's own prototype.html. Every member of a revision family shares ONE
    sandbox, so the working tree is the NEWEST member's file whatever id is in
    the path. Omitting ``ref`` renders the working tree, as before.
    """
    # ── Two-layer IDOR owner check ────────────────────────────────────────
    await _resolve_owned_run(run_id, current_user)

    # ── Resolve sandbox and read prototype.html ───────────────────────────
    chain_root_id = _resolve_chain_root_or_404(run_id, current_user.id)
    sandbox = RunSandbox(current_user.id, chain_root_id, runs_root=settings.RUNS_ROOT)

    if run_dir_expired(sandbox.root):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace expired"
        )

    html_at_ref: bytes | None = None
    if ref is not None:
        safe_ref = _validate_ref(ref, sandbox)
        try:
            html_at_ref = sandbox.read_file_at_ref(safe_ref, "prototype.html")
        except Exception:  # noqa: BLE001 — absent at that version
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="prototype.html not found at this version",
            ) from None
    else:
        try:
            html_path = sandbox.path_for("prototype.html")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path"
            )

        if not html_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="prototype.html not found in this run's workspace",
            )

    # ── Playwright availability check ─────────────────────────────────────
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except Exception as exc:
        logger.warning("figma_export: Playwright unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playwright not available on this server. Use the client-side Figma export instead.",
        ) from exc

    # ── Run extraction ────────────────────────────────────────────────────
    tmp_html: Path | None = None
    try:
        if html_at_ref is not None:
            # Chromium renders a file:// URI, so the tagged bytes go to a temp
            # file in the sandbox's own git-ignored .browser/ scratch: relative
            # references still resolve inside this user's workspace, and no
            # concurrent revision's commit can pick the file up.
            scratch = sandbox.root / ".browser"
            scratch.mkdir(exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "wb", dir=scratch, prefix="figma-", suffix=".html", delete=False
            ) as fh:
                fh.write(html_at_ref)
            html_path = tmp_html = Path(fh.name)
        raw = await _run_playwright_extraction(html_path.as_uri())
    except Exception as exc:
        logger.error("figma_export: extraction failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Figma extraction failed: {exc}",
        ) from exc
    finally:
        if tmp_html is not None:
            tmp_html.unlink(missing_ok=True)

    if not raw or not raw.get("screens"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Extraction returned no screens. The prototype may not have rendered.",
        )

    logger.info("figma_export: run=%s screens=%d", run_id, len(raw["screens"]))

    # Sanitize the IR tree before JSON serialization.
    # getComputedStyle returns "normal", "auto", etc. for some numeric fields
    # (e.g. lineHeight:"normal") which JavaScript's parseFloat() turns into NaN.
    # Python's json.dumps rejects NaN/Infinity — replace them with None.
    sanitized = _sanitize_floats(raw)

    return JSONResponse(
        content={
            "version": 3,
            "screens": sanitized["screens"],
            "viewport": sanitized.get("viewport", {"w": _VIEWPORT_W, "h": _VIEWPORT_H}),
            "tokens": sanitized.get("tokens"),
        }
    )
