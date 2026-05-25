/**
 * Generates a self-contained HTML preview page from a DESIGN.md body.
 *
 * Used for the 134 design systems that don't ship a components.html.
 * Extracts color tokens, typography info, and key metadata from the
 * markdown and renders a clean token showcase page.
 */

import { extractPalette } from "./design-system-colors";

// Extract all hex colors with their surrounding label context
function extractColorTokens(body: string): Array<{ label: string; hex: string }> {
  const tokens: Array<{ label: string; hex: string }> = [];
  const seen = new Set<string>();

  // Match patterns like: **Label** (`#hex`): description
  // or: - **Label** (`#hex`)
  // or: Primary (`#hex`)
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

  // Fallback: use extractPalette if we found nothing
  if (tokens.length === 0) {
    const palette = extractPalette(body, 8);
    palette.forEach((hex, i) => tokens.push({ label: `Color ${i + 1}`, hex }));
  }

  return tokens.slice(0, 16);
}

// Extract font family names from the body
function extractFonts(body: string): string[] {
  const fonts: string[] = [];
  const seen = new Set<string>();

  // Match: **Primary**: `Font Name`, or font-family: "Font Name"
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

// Extract the H1 title
function extractTitle(body: string): string {
  const m = body.match(/^#\s+(.+)/m);
  return m ? m[1].trim() : "Design System";
}

// Extract category and description from blockquotes
function extractMeta(body: string): { category: string; description: string } {
  const catM = body.match(/^>\s*Category:\s*(.+)/m);
  const descM = body.match(/^>\s*Category:[^\n]*\n>\s*(.+)/m);
  return {
    category: catM ? catM[1].trim() : "",
    description: descM ? descM[1].trim() : "",
  };
}

export function generateDesignSystemPreviewHtml(body: string): string {
  const title = extractTitle(body);
  const { category, description } = extractMeta(body);
  const colorTokens = extractColorTokens(body);
  const fonts = extractFonts(body);

  // Pick bg and fg from the tokens if possible
  const bgToken = colorTokens.find((t) =>
    /background|bg|page|canvas|surface/i.test(t.label)
  );
  const fgToken = colorTokens.find((t) =>
    /^(primary\s*text|foreground|fg|text|heading)/i.test(t.label)
  );
  const accentToken = colorTokens.find((t) =>
    /accent|primary|brand|cta|action/i.test(t.label)
  );

  const bg = bgToken?.hex ?? "#ffffff";
  const fg = fgToken?.hex ?? "#111827";
  const accent = accentToken?.hex ?? "#2563eb";
  const fontFamily = fonts[0]
    ? `"${fonts[0]}", ui-sans-serif, system-ui, sans-serif`
    : "ui-sans-serif, system-ui, sans-serif";

  const colorSwatches = colorTokens
    .map(
      ({ label, hex }) => `
      <div class="swatch">
        <div class="swatch-color" style="background:${hex}"></div>
        <div class="swatch-label">${escHtml(label)}</div>
        <div class="swatch-hex">${hex}</div>
      </div>`
    )
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
  .header{margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid rgba(128,128,128,0.15)}
  .title{font-size:22px;font-weight:700;letter-spacing:-0.3px;margin-bottom:4px}
  .meta{font-size:12px;opacity:0.5;display:flex;gap:12px;flex-wrap:wrap}
  .section{margin-bottom:28px}
  .section-label{font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;opacity:0.4;margin-bottom:12px}
  .swatches{display:flex;flex-wrap:wrap;gap:10px}
  .swatch{width:80px}
  .swatch-color{height:48px;border-radius:8px;border:1px solid rgba(128,128,128,0.12);margin-bottom:5px}
  .swatch-label{font-size:10px;font-weight:600;opacity:0.7;line-height:1.3;margin-bottom:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .swatch-hex{font-size:10px;font-family:ui-monospace,monospace;opacity:0.45}
  .font-pills{display:flex;flex-wrap:wrap;gap:8px}
  .font-pill{background:rgba(128,128,128,0.08);border:1px solid rgba(128,128,128,0.12);border-radius:6px;padding:4px 10px;font-size:12px;font-weight:500}
  .type-specimen{display:flex;flex-direction:column;gap:10px}
  .type-row{display:flex;align-items:baseline;gap:12px}
  .type-label{font-size:10px;opacity:0.35;width:60px;flex-shrink:0;font-family:ui-monospace,monospace}
  .btn-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .btn{display:inline-flex;align-items:center;justify-content:center;border-radius:6px;padding:8px 16px;font-size:13px;font-weight:600;cursor:default;border:none}
  .btn-primary{background:${accent};color:#fff}
  .btn-secondary{background:transparent;color:${fg};border:1px solid rgba(128,128,128,0.25)}
  .btn-ghost{background:rgba(128,128,128,0.08);color:${fg}}
  .card{background:rgba(128,128,128,0.05);border:1px solid rgba(128,128,128,0.12);border-radius:10px;padding:16px}
  .card-title{font-size:14px;font-weight:600;margin-bottom:4px}
  .card-body{font-size:12px;opacity:0.55;line-height:1.5}
  .input{width:100%;max-width:280px;border:1px solid rgba(128,128,128,0.25);border-radius:6px;padding:8px 12px;font-size:13px;background:transparent;color:${fg};outline:none}
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
      <div class="type-row"><span class="type-label">32px</span><span style="font-size:32px;font-weight:700;letter-spacing:-0.5px">Display heading</span></div>
      <div class="type-row"><span class="type-label">24px</span><span style="font-size:24px;font-weight:600">Section heading</span></div>
      <div class="type-row"><span class="type-label">16px</span><span style="font-size:16px">Body text — the quick brown fox jumps over the lazy dog.</span></div>
      <div class="type-row"><span class="type-label">12px</span><span style="font-size:12px;opacity:0.55">Caption and metadata text</span></div>
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
