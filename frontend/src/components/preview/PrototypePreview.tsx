"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Layout, ExternalLink, RefreshCw,
  ZoomIn, ZoomOut, Code2, Copy, Check, X, Sliders,
} from "lucide-react";
import { useClipboardCopy } from "@/hooks/useClipboardCopy";
import { utf8Bytes } from "@/lib/byteSize";
import { TweaksPanel, DEFAULT_TOKENS, FONT_OPTIONS, type TokenMap } from "./TweaksPanel";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
  onRevise?: (instruction: string) => void;
}

const ZOOM_LEVELS = [50, 67, 75, 90, 100, 110, 125, 150, 175, 200];
const DEFAULT_ZOOM_INDEX = 4; // 100%

/** Strip markdown fences and artifact tags, return clean HTML string. */
function stripFences(raw: string): string {
  let s = raw.trim();
  // Strip markdown fences
  if (s.startsWith("```")) {
    s = s.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
  }
  // Strip <artifact>...</artifact> wrapper (prototype finalizer wraps output in these)
  const artifactMatch = s.match(/<artifact[^>]*>\s*([\s\S]*?)\s*<\/artifact>/i);
  if (artifactMatch) {
    s = artifactMatch[1].trim();
  }
  // Find HTML start if there's preamble text before <!DOCTYPE
  const htmlStart = s.search(/<!DOCTYPE\s+html|<html[\s>]/i);
  if (htmlStart > 0) {
    s = s.slice(htmlStart);
  }
  return s;
}

/**
 * Build a <style> override block from the token map.
 *
 * Strategy: use the universal selector * with !important for ALL color and
 * font properties. This is the only approach that reliably overrides:
 * - Hardcoded hex values in class rules
 * - Inline styles set by JavaScript
 * - Highly specific selectors in design system CSS
 * - CSS custom properties with unknown names
 *
 * We then selectively restore accent colors on interactive elements.
 */
function buildTweakStyle(tokens: TokenMap): string {
  const bg = tokens["--bg"];
  const fg = tokens["--fg"];
  const accent = tokens["--accent"];
  const accentFg = tokens["--accent-fg"];
  const surface = tokens["--surface"];
  const border = tokens["--border"];
  const muted = tokens["--muted"];
  const font = tokens["--font-sans"];

  // Compute a slightly lighter/darker surface for alternating rows
  // so tables remain readable on any background
  const isLight = (hex: string) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 128;
  };
  const bgIsLight = isLight(bg.startsWith("#") && bg.length >= 7 ? bg : "#ffffff");
  const altRow = bgIsLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.06)";
  const hoverBg = bgIsLight ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.08)";

  return `
/* ══════════════════════════════════════════════════════
   Flowin Tweaks — universal override
   ══════════════════════════════════════════════════════ */

/* 1. CSS variable overrides — covers var() usage */
:root, [data-theme], [class*="theme-"] {
  --bg: ${bg} !important;
  --fg: ${fg} !important;
  --accent: ${accent} !important;
  --accent-fg: ${accentFg} !important;
  --surface: ${surface} !important;
  --border: ${border} !important;
  --muted: ${muted} !important;
  --font-sans: ${font} !important;
  --font-display: ${font} !important;
  --font-body: ${font} !important;
  --font-family: ${font} !important;
  /* shadcn/radix names */
  --background: ${bg} !important;
  --foreground: ${fg} !important;
  --card: ${surface} !important;
  --card-foreground: ${fg} !important;
  --primary: ${accent} !important;
  --primary-foreground: ${accentFg} !important;
  --secondary: ${surface} !important;
  --secondary-foreground: ${fg} !important;
  --muted-foreground: ${muted} !important;
  --border-color: ${border} !important;
  /* common alt names */
  --color-bg: ${bg} !important;
  --color-text: ${fg} !important;
  --color-primary: ${accent} !important;
  --color-surface: ${surface} !important;
  --color-border: ${border} !important;
  --color-muted: ${muted} !important;
  --text-primary: ${fg} !important;
  --text-secondary: ${muted} !important;
  --bg-primary: ${bg} !important;
  --bg-secondary: ${surface} !important;
}

/* 2. Universal font — hits every element without exception */
*, *::before, *::after {
  font-family: ${font} !important;
  box-sizing: border-box;
}

/* 3. Universal background + text — the nuclear option.
   We set background to transparent by default so elements
   inherit from their nearest opaque ancestor, then set
   the root backgrounds explicitly. */
* {
  color: ${fg} !important;
  border-color: ${border} !important;
}

/* 4. Root backgrounds */
html {
  background-color: ${bg} !important;
}
body {
  background-color: ${bg} !important;
  color: ${fg} !important;
}

/* 5. Layout containers — force bg */
body > *,
[data-page],
[id="app"], [id="root"], [id="__next"], [id="main"],
[class*="app"], [class*="layout"], [class*="wrapper"],
[class*="container"], [class*="page-"] {
  background-color: ${bg} !important;
  color: ${fg} !important;
}

/* 6. Sidebar / nav — use surface */
aside, nav,
[class*="sidebar"], [class*="side-bar"],
[class*="navbar"], [class*="nav-bar"],
[class*="topbar"], [class*="top-bar"],
[class*="sidenav"], [class*="side-nav"] {
  background-color: ${surface} !important;
  border-color: ${border} !important;
  color: ${fg} !important;
}

/* 7. Header */
header, [class*="header"], [role="banner"] {
  background-color: ${surface} !important;
  border-color: ${border} !important;
  color: ${fg} !important;
}

/* 8. Cards, panels, modals */
[class*="card"], [class*="panel"], [class*="widget"],
[class*="tile"], [class*="box-"],
[class*="modal"], [class*="dialog"],
[class*="dropdown"], [class*="popover"],
[class*="tooltip"], [class*="sheet"],
[role="dialog"], [role="tooltip"] {
  background-color: ${surface} !important;
  border-color: ${border} !important;
  color: ${fg} !important;
}

/* 9. Main content area */
main, [role="main"], article, section,
[class*="content"], [class*="main-"] {
  background-color: ${bg} !important;
  color: ${fg} !important;
}

/* 10. Tables */
table { border-color: ${border} !important; }
thead, thead tr, thead th {
  background-color: ${surface} !important;
  color: ${fg} !important;
  border-color: ${border} !important;
}
tbody tr:nth-child(even) {
  background-color: ${altRow} !important;
}
tbody tr:nth-child(odd) {
  background-color: transparent !important;
}
td, th {
  color: ${fg} !important;
  border-color: ${border} !important;
}

/* 11. Inputs */
input, textarea, select, [contenteditable] {
  background-color: ${surface} !important;
  color: ${fg} !important;
  border-color: ${border} !important;
}
input::placeholder, textarea::placeholder {
  color: ${muted} !important;
  opacity: 1 !important;
}

/* 12. Buttons — base style */
button, [role="button"],
[class*="btn"], [class*="button"] {
  background-color: ${surface} !important;
  color: ${fg} !important;
  border-color: ${border} !important;
}

/* 13. Primary / accent buttons — restore accent color */
[class*="btn-primary"], [class*="button-primary"],
[class*="btn-accent"], [class*="btn-cta"],
[class*="primary-btn"], [class*="cta-btn"],
[class*="submit"], [type="submit"] {
  background-color: ${accent} !important;
  color: ${accentFg} !important;
  border-color: ${accent} !important;
}

/* 14. Links */
a { color: ${accent} !important; }
a:visited { color: ${accent} !important; }

/* 15. Muted / secondary text */
[class*="muted"], [class*="text-muted"],
[class*="secondary"], [class*="text-secondary"],
[class*="subtitle"], [class*="caption"],
[class*="hint"], [class*="helper"],
[class*="label"], small, figcaption, caption {
  color: ${muted} !important;
}

/* 16. Nav items — active state */
[class*="nav-item"][class*="active"],
[class*="nav-link"][class*="active"],
[class*="menu-item"][class*="active"],
[aria-current="page"] {
  color: ${accent} !important;
  background-color: ${hoverBg} !important;
}

/* 17. Hover states */
[class*="nav-item"]:hover,
[class*="nav-link"]:hover,
[class*="menu-item"]:hover,
button:hover, [role="button"]:hover {
  background-color: ${hoverBg} !important;
}

/* 18. Badges, tags, chips */
[class*="badge"], [class*="tag"], [class*="chip"],
[class*="pill"], [class*="label-"] {
  background-color: ${surface} !important;
  color: ${fg} !important;
  border-color: ${border} !important;
}

/* 19. Dividers */
hr, [class*="divider"], [class*="separator"] {
  background-color: ${border} !important;
  border-color: ${border} !important;
}

/* 20. Scrollbars */
::-webkit-scrollbar { background-color: ${bg} !important; }
::-webkit-scrollbar-thumb { background-color: ${border} !important; }
`.trim();
}

/**
 * Inject the tweaks style block into an HTML string.
 * Also injects a Google Fonts <link> tag when the selected font requires it.
 * Replaces any existing flowin-tweaks block, or appends before </body>.
 */
function injectTweaksIntoHtml(html: string, tokens: TokenMap): string {
  const style = buildTweakStyle(tokens);
  const block = `<style id="flowin-tweaks">\n${style}\n</style>`;

  // Remove existing tweaks block and font link
  let cleaned = html.replace(/<style id="flowin-tweaks">[\s\S]*?<\/style>/gi, "");
  cleaned = cleaned.replace(/<link id="flowin-font"[^>]*>/gi, "");

  // Inject Google Fonts link if the selected font needs it
  const fontOption = FONT_OPTIONS.find((f) => f.value === tokens["--font-sans"]);
  const fontLink = fontOption?.googleFont
    ? `<link id="flowin-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=${fontOption.googleFont}&display=swap">`
    : "";

  // Inject into <head> if possible, otherwise prepend
  if (fontLink) {
    if (/<\/head>/i.test(cleaned)) {
      cleaned = cleaned.replace(/<\/head>/i, `${fontLink}\n</head>`);
    } else if (/<head[^>]*>/i.test(cleaned)) {
      cleaned = cleaned.replace(/(<head[^>]*>)/i, `$1\n${fontLink}`);
    }
  }

  // Inject tweaks style before </body>
  if (/<\/body>/i.test(cleaned)) {
    return cleaned.replace(/<\/body>/i, `${block}\n</body>`);
  }
  return cleaned + "\n" + block;
}

export function PrototypePreview({ content, isStreaming, onRevise }: PrototypePreviewProps) {
  const [revisionText, setRevisionText] = useState("");
  const [baseHtml, setBaseHtml] = useState<string>("");
  const [renderedHtml, setRenderedHtml] = useState<string>("");
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [showSource, setShowSource] = useState(false);
  const [showTweaks, setShowTweaks] = useState(false);
  const { copied, failed, copy } = useClipboardCopy();
  const [tokens, setTokens] = useState<TokenMap>({ ...DEFAULT_TOKENS });
  const [tweaksActive, setTweaksActive] = useState(false);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const rebuildTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tokensRef = useRef<TokenMap>({ ...DEFAULT_TOKENS });
  const baseHtmlRef = useRef<string>("");

  const zoom = ZOOM_LEVELS[zoomIndex];

  // ── Sync baseHtml when content changes ─────────────────────────────────
  useEffect(() => {
    if (!content) {
      setBaseHtml("");
      baseHtmlRef.current = "";
      setRenderedHtml("");
      return;
    }
    const stripped = stripFences(content);
    setBaseHtml(stripped);
    baseHtmlRef.current = stripped;
    setTokens({ ...DEFAULT_TOKENS });
    tokensRef.current = { ...DEFAULT_TOKENS };
    setTweaksActive(false);
    setRenderedHtml(stripped); // start with clean HTML, no tweaks
  }, [content]);

  // ── Build Blob URL whenever renderedHtml changes ────────────────────────
  useEffect(() => {
    if (!renderedHtml) { setBlobUrl(null); return; }
    const isHtml = /<!DOCTYPE\s+html|<html[\s>]/i.test(renderedHtml);
    if (!isHtml) { setBlobUrl(null); return; }
    const blob = new Blob([renderedHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    setBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [renderedHtml]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);
    };
  }, []);

  // ── Rebuild blob with current tokens (debounced 400ms) ─────────────────
  const scheduleRebuild = useCallback(() => {
    if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);
    rebuildTimerRef.current = setTimeout(() => {
      if (!baseHtmlRef.current) return;
      const html = injectTweaksIntoHtml(baseHtmlRef.current, tokensRef.current);
      setRenderedHtml(html);
    }, 400);
  }, []);

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleZoomIn = useCallback(() => setZoomIndex((i) => Math.min(i + 1, ZOOM_LEVELS.length - 1)), []);
  const handleZoomOut = useCallback(() => setZoomIndex((i) => Math.max(i - 1, 0)), []);
  const handleZoomReset = useCallback(() => setZoomIndex(DEFAULT_ZOOM_INDEX), []);
  const handleOpenInNewTab = useCallback(() => { if (blobUrl) window.open(blobUrl, "_blank"); }, [blobUrl]);

  const handleCopySource = useCallback(() => {
    if (!renderedHtml) return;
    void copy(renderedHtml);
  }, [renderedHtml, copy]);

  const handleTokenChange = useCallback((key: keyof TokenMap, value: string) => {
    setTokens((prev) => {
      const next = { ...prev, [key]: value };
      tokensRef.current = next;
      return next;
    });
    setTweaksActive(true);
    scheduleRebuild();
  }, [scheduleRebuild]);

  const handleApplyPreset = useCallback((partial: Partial<TokenMap>) => {
    setTokens((prev) => {
      const next = { ...prev, ...partial };
      tokensRef.current = next;
      return next;
    });
    setTweaksActive(true);
    // Preset: rebuild immediately (no debounce)
    if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);
    // Use setTimeout(0) to let the state update flush first
    setTimeout(() => {
      if (!baseHtmlRef.current) return;
      const html = injectTweaksIntoHtml(baseHtmlRef.current, tokensRef.current);
      setRenderedHtml(html);
    }, 0);
  }, []);

  const handleApplyHtml = useCallback((html: string) => {
    const stripped = html.replace(/<style id="flowin-tweaks">[\s\S]*?<\/style>/gi, "").trim();
    baseHtmlRef.current = stripped;
    setBaseHtml(stripped);
    const final = tweaksActive
      ? injectTweaksIntoHtml(stripped, tokensRef.current)
      : stripped;
    setRenderedHtml(final);
  }, [tweaksActive]);

  const handleReset = useCallback(() => {
    if (rebuildTimerRef.current) clearTimeout(rebuildTimerRef.current);
    setTokens({ ...DEFAULT_TOKENS });
    tokensRef.current = { ...DEFAULT_TOKENS };
    setTweaksActive(false);
    setRenderedHtml(baseHtmlRef.current);
  }, []);

  // ── Empty / streaming / non-HTML states ────────────────────────────────

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 mb-4">
          <Layout className="h-7 w-7 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-600 mb-1">No Preview Yet</p>
        <p className="text-xs text-gray-400 text-center max-w-[200px]">
          Run the pipeline to generate your prototype.
        </p>
      </div>
    );
  }

  if (isStreaming) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
          <Layout className="h-6 w-6 text-gray-400" />
        </div>
        <p className="text-[11px] text-gray-500 font-medium">Building prototype...</p>
      </div>
    );
  }

  if (!blobUrl) {
    const mightBeHtml = /<!DOCTYPE\s+html|<html[\s>]/i.test(renderedHtml || baseHtml);
    if (mightBeHtml) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
            <Layout className="h-6 w-6 text-gray-400" />
          </div>
          <p className="text-[11px] text-gray-500 font-medium">Loading preview...</p>
        </div>
      );
    }
    return (
      <div className="p-4 h-full overflow-auto">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-400 mb-2">Output (text format):</p>
          <pre className="text-[11px] text-gray-900 whitespace-pre-wrap leading-relaxed overflow-auto max-h-[500px]">
            {renderedHtml || baseHtml}
          </pre>
        </div>
      </div>
    );
  }

  // ── Main render ─────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col" style={{ background: "#f5f5f0" }}>

      {/* Browser chrome */}
      <div className="flex-shrink-0 bg-white border-b border-gray-200 px-3 py-2 flex items-center gap-2">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div className="w-2.5 h-2.5 rounded-full bg-gray-200" />
          <div className="w-2.5 h-2.5 rounded-full bg-gray-200" />
          <div className="w-2.5 h-2.5 rounded-full bg-gray-200" />
        </div>
        <div className="flex items-center gap-2 bg-gray-100 rounded-md px-2.5 py-1 min-w-0 flex-1 max-w-[200px]">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
          <span className="text-[10px] text-gray-500 font-mono truncate">prototype.preview</span>
        </div>

        <div className="flex items-center gap-1 ml-auto">
          <button onClick={handleZoomOut} disabled={zoomIndex === 0} title="Zoom out"
            className="flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 transition-colors">
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <button onClick={handleZoomReset} title="Reset zoom (100%)"
            className="flex h-6 min-w-[38px] items-center justify-center rounded px-1 text-[10px] font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors tabular-nums">
            {zoom}%
          </button>
          <button onClick={handleZoomIn} disabled={zoomIndex === ZOOM_LEVELS.length - 1} title="Zoom in"
            className="flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 disabled:opacity-30 transition-colors">
            <ZoomIn className="h-3.5 w-3.5" />
          </button>

          <div className="w-px h-4 bg-gray-200 mx-0.5" />

          <button
            onClick={() => { setShowTweaks((v) => !v); setShowSource(false); }}
            title={showTweaks ? "Close tweaks" : "Open tweaks panel"}
            className={`flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium transition-colors ${
              showTweaks ? "bg-[#1B2A4A] text-white" : "text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            }`}
          >
            <Sliders className="h-3.5 w-3.5" />
            <span>Tweaks</span>
            {tweaksActive && <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 flex-shrink-0" />}
          </button>

          <button
            onClick={() => { setShowSource((v) => !v); setShowTweaks(false); }}
            title={showSource ? "Hide source" : "View source"}
            className={`flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium transition-colors ${
              showSource ? "bg-[#1B2A4A] text-white" : "text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            }`}
          >
            <Code2 className="h-3.5 w-3.5" />
            <span>Source</span>
          </button>

          <button onClick={handleOpenInNewTab} title="Open in new tab"
            className="flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors">
            <ExternalLink className="h-3.5 w-3.5" />
            <span>Open</span>
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        <div className="flex-1 min-w-0 overflow-hidden">
          {showSource ? (
            <div className="h-full flex flex-col bg-[#0f1117]">
              <div className="flex items-center justify-between px-4 py-2 border-b border-white/[0.06] flex-shrink-0">
                <div className="flex items-center gap-2">
                  <Code2 className="h-3.5 w-3.5 text-gray-400" />
                  <span className="text-[11px] font-medium text-gray-300">index.html</span>
                  <span className="text-[10px] text-gray-500">
                    {(utf8Bytes(renderedHtml) / 1024).toFixed(1)} KB · {renderedHtml.split("\n").length} lines
                  </span>
                  {tweaksActive && (
                    <span className="rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-medium text-amber-400">tweaks applied</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={handleCopySource}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] font-medium transition-all ${
                      copied ? "bg-emerald-500/20 text-emerald-400" : "bg-white/[0.06] text-gray-300 hover:bg-white/[0.1]"
                    }`}>
                    {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> {failed ? "Copy failed" : "Copy all"}</>}
                  </button>
                  <button onClick={() => setShowSource(false)}
                    className="flex h-6 w-6 items-center justify-center rounded text-gray-500 hover:bg-white/[0.06] hover:text-gray-300 transition-colors">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-auto">
                <pre className="p-4 text-[11px] leading-relaxed text-gray-300 font-mono whitespace-pre-wrap break-words"
                  style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace" }}>
                  {renderedHtml}
                </pre>
              </div>
            </div>
          ) : (
            <div className="h-full w-full overflow-auto">
              <div style={{
                width: zoom === 100 ? "100%" : `${(100 / zoom) * 100}%`,
                height: zoom === 100 ? "100%" : `${(100 / zoom) * 100}%`,
                transform: `scale(${zoom / 100})`,
                transformOrigin: "top left",
                minHeight: "100%",
              }}>
                <iframe
                  ref={iframeRef}
                  key={blobUrl}
                  src={blobUrl}
                  className="w-full h-full border-0"
                  style={{ minHeight: "600px" }}
                  sandbox="allow-scripts allow-same-origin"
                  title="Prototype Preview"
                />
              </div>
            </div>
          )}
        </div>

        {showTweaks && (
          <TweaksPanel
            tokens={tokens}
            editHtml={baseHtml}
            onTokenChange={handleTokenChange}
            onApplyPreset={handleApplyPreset}
            onApplyHtml={handleApplyHtml}
            onReset={handleReset}
            onClose={() => setShowTweaks(false)}
          />
        )}
      </div>

      {/* Revision bar */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
          <input
            type="text"
            aria-label="Revision instructions"
            name="prototype-revision"
            value={revisionText}
            onChange={(e) => setRevisionText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            placeholder='Request changes, e.g. "Add a Reports page" or "Change the dashboard stats"'
            className="flex-1 text-[12px] text-gray-700 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-gray-400 transition-colors"
          />
          <button
            onClick={() => {
              if (revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            disabled={!revisionText.trim()}
            className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-[#1B2A4A] hover:bg-[#2a3d5e] disabled:opacity-40 rounded-lg px-3 py-2 transition-colors flex-shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Revise
          </button>
        </div>
      )}
    </div>
  );
}
