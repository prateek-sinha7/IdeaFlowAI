/**
 * Generates a self-contained HTML preview page from a DESIGN.md body.
 *
 * Used for the 134 design systems that don't ship a components.html.
 * Extracts color tokens, typography info, and key metadata from the
 * markdown and renders a clean token showcase page.
 *
 * Root cause fix: dark design systems (Linear, Discord, GitHub dark, etc.)
 * have near-black backgrounds. The original code fell back to fg=#111827
 * (dark gray) when no foreground token was found — invisible on dark bg.
 * Fix: (1) broader fg token patterns, (2) luminance-based safe default,
 * (3) WCAG AA contrast enforcement as a final safety net.
 */

import { extractPalette } from "./design-system-colors";

// ---------------------------------------------------------------------------
// Contrast helpers
// ---------------------------------------------------------------------------

function hexToRgbValues(hex: string): [number, number, number] | null {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
  if (h.length === 8) h = h.slice(0, 6);
  if (h.length !== 6) return null;
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance(hex: string): number {
  const rgb = hexToRgbValues(hex);
  if (!rgb) return 0.5;
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function isDark(hex: string): boolean {
  return luminance(hex) < 0.18;
}

/**
 * Ensures fg has at least 4.5:1 contrast ratio against bg (WCAG AA).
 * If not, overrides with white (dark bg) or near-black (light bg).
 */
function ensureContrast(bg: string, fg: string): string {
  const bgL = luminance(bg) + 0.05;
  const fgL = luminance(fg) + 0.05;
  const ratio = bgL > fgL ? bgL / fgL : fgL / bgL;
  if (ratio >= 4.5) return fg;
  return isDark(bg) ? "#f0f0f0" : "#111111";
}

// ---------------------------------------------------------------------------
// Extraction helpers
// ---------------------------------------------------------------------------

function extractColorTokens(body: string): Array<{ label: string; hex: string }> {
  const tokens: Array<{ label: string; hex: string }> = [];
  const seen = new Set<string>();

  const patterns = [
    /\*\*([^*]+)\*\*\s*\(`(#[0-9a-fA-F]{3,8})`\)/g,
    /\*\*([^*]+)\*\*\s*\(`(#[0-9a-fA-F]{3,8})`\s*\/\s*`#[0-9a-fA-F]{3,8}`\)/g,
    /[-–]\s*\*\*([^*]+)\*\*[^`]*`(#[0-9a-fA-F]{3,8})`/g,
    /([A-Z][a-zA-Z\s]+)\s*\(`(#[0-9a-fA-F]{3,8})`\)/g,
  ];

  for (const re of patterns) {
    for (const m of body.matchAll(re)) {
      const label = m[1].trim();
      const hex = m[2].toLowerCase();
      if (!seen.has(hex) && label.length < 40) {
        seen.add(hex);
        tokens.push({ label, hex });
      }
    }
  }

  if (tokens.length === 0) {
    const palette = extractPalette(body, 8);
    palette.forEach((hex, i) => tokens.push({ label: `Color ${i + 1}`, hex }));
  }

  return tokens.slice(0, 16);
}

function extractFonts(body: string): string[] {
  const fonts: string[] = [];
  const seen = new Set<string>();

  const patterns = [
    /\*\*(?:Primary|Display|Body|Heading|Sans|Serif|Mono)[^*]*\*\*[^`\n]*`([^`]+)`/gi,
    /font[-\s]family[^:]*:\s*[`"]?([A-Z][a-zA-Z\s]+(?:Variable)?)[`"]?/gi,
    /\*\*(?:Primary|Display|Body)[^*]*\*\*[^:\n]*:\s*([A-Z][a-zA-Z\s]+(?:Variable)?)/gi,
  ];

  for (const re of patterns) {
    for (const m of body.matchAll(re)) {
      const font = m[1].trim().split(",")[0].trim().replace(/[`'"]/g, "");
      if (font.length > 2 && font.length < 40 && !seen.has(font)) {
        seen.add(font);
        fonts.push(font);
      }
    }
  }

  return fonts.slice(0, 3);
}

function extractTitle(body: string): string {
  const m = body.match(/^#\s+(.+)/m);
  return m ? m[1].trim() : "Design System";
}

function extractMeta(body: string): { category: string; description: string } {
  const catM = body.match(/^>\s*Category:\s*(.+)/m);
  const descM = body.match(/^>\s*Category:[^\n]*\n>\s*(.+)/m);
  return {
    category: catM ? catM[1].trim() : "",
    description: descM ? descM[1].trim() : "",
  };
}

// ---------------------------------------------------------------------------
// Main generator
// ---------------------------------------------------------------------------

export function generateDesignSystemPreviewHtml(body: string): string {
  const title = extractTitle(body);
  const { category, description } = extractMeta(body);
  const colorTokens = extractColorTokens(body);
  const fonts = extractFonts(body);

  // ── Background ──────────────────────────────────────────────────────
  const bgToken = colorTokens.find((t) =>
    /background|bg|page|canvas|surface|marketing.black|panel.dark|base/i.test(t.label)
  );
  const bg = bgToken?.hex ?? "#ffffff";
  const dark = isDark(bg);

  // ── Foreground ──────────────────────────────────────────────────────
  // Broadened pattern covers dark-mode labels: "Primary White", "Primary Text",
  // "Foreground", "fg", "text", "heading", "content", "on-bg", "on-surface"
  const fgToken = colorTokens.find((t) =>
    /^(primary\s*(text|white|fg)|foreground|fg|text|heading|content|body\s*text|on.bg|on.surface)/i.test(t.label)
  );
  // Safe default: white for dark bg, near-black for light bg
  const rawFg = fgToken?.hex ?? (dark ? "#f0f0f0" : "#111827");
  // Final WCAG AA safety net — guarantees readability regardless of token quality
  const fg = ensureContrast(bg, rawFg);

  // ── Accent ──────────────────────────────────────────────────────────
  const accentToken = colorTokens.find((t) =>
    /accent|primary|brand|cta|action/i.test(t.label)
  );
  const accent = accentToken?.hex ?? "#2563eb";
  // Ensure accent text is readable (white or black depending on accent luminance)
  const accentFg = isDark(accent) ? "#ffffff" : "#111111";

  // ── Adaptive UI colors ──────────────────────────────────────────────
  // All UI chrome adapts to dark/light mode so labels are always readable
  const borderColor      = dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.1)";
  const sectionLabel     = dark ? "rgba(255,255,255,0.4)"  : "rgba(0,0,0,0.35)";
  const swatchLabel      = dark ? "rgba(255,255,255,0.75)" : "rgba(0,0,0,0.65)";
  const swatchHex        = dark ? "rgba(255,255,255,0.45)" : "rgba(0,0,0,0.4)";
  const metaColor        = dark ? "rgba(255,255,255,0.5)"  : "rgba(0,0,0,0.45)";
  const typeLabel        = dark ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.3)";
  const cardBg           = dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)";
  const cardBorder       = dark ? "rgba(255,255,255,0.1)"  : "rgba(0,0,0,0.1)";
  const cardBodyColor    = dark ? "rgba(255,255,255,0.55)" : "rgba(0,0,0,0.5)";
  const inputBorder      = dark ? "rgba(255,255,255,0.2)"  : "rgba(0,0,0,0.2)";
  const btnSecBorder     = dark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.2)";
  const btnGhostBg       = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  const fontPillBg       = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
  const fontPillBorder   = dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.1)";

  // ── Font ────────────────────────────────────────────────────────────
  const fontFamily = fonts[0]
    ? `"${fonts[0]}", ui-sans-serif, system-ui, sans-serif`
    : "ui-sans-serif, system-ui, sans-serif";

  // ── Swatches ────────────────────────────────────────────────────────
  const colorSwatches = colorTokens
    .map(({ label, hex }) => `
      <div class="swatch">
        <div class="swatch-color" style="background:${hex}"></div>
        <div class="swatch-label">${escHtml(label)}</div>
        <div class="swatch-hex">${hex}</div>
      </div>`)
    .join("");

  const fontPills = fonts
    .map((f) => `<span class="font-pill">${escHtml(f)}</span>`)
    .join("");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>${escHtml(title)}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:${bg};color:${fg};font-family:${fontFamily};font-size:14px;line-height:1.6;padding:32px 40px;min-height:100vh}
  .header{margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid ${borderColor}}
  .title{font-size:22px;font-weight:700;letter-spacing:-0.3px;margin-bottom:4px;color:${fg}}
  .meta{font-size:12px;color:${metaColor};display:flex;gap:12px;flex-wrap:wrap}
  .section{margin-bottom:28px}
  .section-label{font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:${sectionLabel};margin-bottom:12px}
  .swatches{display:flex;flex-wrap:wrap;gap:10px}
  .swatch{width:80px}
  .swatch-color{height:48px;border-radius:8px;border:1px solid ${borderColor};margin-bottom:5px}
  .swatch-label{font-size:10px;font-weight:600;color:${swatchLabel};line-height:1.3;margin-bottom:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .swatch-hex{font-size:10px;font-family:ui-monospace,monospace;color:${swatchHex}}
  .font-pills{display:flex;flex-wrap:wrap;gap:8px}
  .font-pill{background:${fontPillBg};border:1px solid ${fontPillBorder};border-radius:6px;padding:4px 10px;font-size:12px;font-weight:500;color:${fg}}
  .type-specimen{display:flex;flex-direction:column;gap:10px}
  .type-row{display:flex;align-items:baseline;gap:12px}
  .type-label{font-size:10px;color:${typeLabel};width:60px;flex-shrink:0;font-family:ui-monospace,monospace}
  .btn-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .btn{display:inline-flex;align-items:center;justify-content:center;border-radius:6px;padding:8px 16px;font-size:13px;font-weight:600;cursor:default;border:none}
  .btn-primary{background:${accent};color:${accentFg}}
  .btn-secondary{background:transparent;color:${fg};border:1px solid ${btnSecBorder}}
  .btn-ghost{background:${btnGhostBg};color:${fg};border:none}
  .card{background:${cardBg};border:1px solid ${cardBorder};border-radius:10px;padding:16px}
  .card-title{font-size:14px;font-weight:600;margin-bottom:4px;color:${fg}}
  .card-body{font-size:12px;color:${cardBodyColor};line-height:1.5}
  .input{width:100%;max-width:280px;border:1px solid ${inputBorder};border-radius:6px;padding:8px 12px;font-size:13px;background:transparent;color:${fg};outline:none}
</style>
</head>
<body>
  <div class="header">
    <div class="title">${escHtml(title)}</div>
    <div class="meta">
      ${category ? `<span>${escHtml(category)}</span>` : ""}
      ${description ? `<span>${escHtml(description)}</span>` : ""}
    </div>
  </div>

  ${colorTokens.length > 0 ? `
  <div class="section">
    <div class="section-label">Color Palette</div>
    <div class="swatches">${colorSwatches}</div>
  </div>` : ""}

  ${fonts.length > 0 ? `
  <div class="section">
    <div class="section-label">Typography</div>
    <div class="font-pills">${fontPills}</div>
    <div class="type-specimen" style="margin-top:16px">
      <div class="type-row"><span class="type-label">32px</span><span style="font-size:32px;font-weight:700;letter-spacing:-0.5px;color:${fg}">Display heading</span></div>
      <div class="type-row"><span class="type-label">24px</span><span style="font-size:24px;font-weight:600;color:${fg}">Section heading</span></div>
      <div class="type-row"><span class="type-label">16px</span><span style="font-size:16px;color:${fg}">Body text — the quick brown fox jumps over the lazy dog.</span></div>
      <div class="type-row"><span class="type-label">12px</span><span style="font-size:12px;color:${cardBodyColor}">Caption and metadata text</span></div>
    </div>
  </div>` : ""}

  <div class="section">
    <div class="section-label">Components</div>
    <div class="btn-row" style="margin-bottom:12px">
      <button class="btn btn-primary">Primary action</button>
      <button class="btn btn-secondary">Secondary</button>
      <button class="btn btn-ghost">Ghost</button>
    </div>
    <div style="margin-bottom:12px">
      <input class="input" placeholder="Input field placeholder…" readonly/>
    </div>
    <div class="card">
      <div class="card-title">Card component</div>
      <div class="card-body">A surface-level container with border and subtle background. Used for grouping related content.</div>
    </div>
  </div>
</body>
</html>`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
