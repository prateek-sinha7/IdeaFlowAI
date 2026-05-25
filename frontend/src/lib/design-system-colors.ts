/**
 * Extracts a representative 4-color palette from a DESIGN.md body.
 *
 * Strategy (mirrors open-design's approach):
 * 1. Find all hex color tokens in the document (#rgb, #rrggbb, #rrggbbaa)
 * 2. Exclude near-white (#f*), near-black (#0*, #1*), and transparent values
 * 3. Deduplicate and pick the 4 most "interesting" colors — preferring
 *    saturated, mid-lightness values that represent the brand palette
 * 4. Fall back to any hex colors if no saturated ones are found
 *
 * Returns an array of 1–4 hex strings, or [] if none found.
 */

const HEX_RE = /#([0-9a-fA-F]{3,8})\b/g;

function hexToRgb(hex: string): [number, number, number] | null {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (h.length === 8) h = h.slice(0, 6); // strip alpha
  if (h.length !== 6) return null;
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return [h * 360, s * 100, l * 100];
}

function isInteresting(hex: string): boolean {
  const rgb = hexToRgb(hex);
  if (!rgb) return false;
  const [, s, l] = rgbToHsl(...rgb);
  // Must have some saturation and not be near-white or near-black
  return s > 8 && l > 8 && l < 92;
}

function colorDistance(a: string, b: string): number {
  const ra = hexToRgb(a), rb = hexToRgb(b);
  if (!ra || !rb) return 0;
  return Math.sqrt(
    Math.pow(ra[0] - rb[0], 2) +
    Math.pow(ra[1] - rb[1], 2) +
    Math.pow(ra[2] - rb[2], 2)
  );
}

/** Pick up to `n` colors that are visually distinct from each other. */
function pickDistinct(colors: string[], n: number, minDist = 40): string[] {
  const picked: string[] = [];
  for (const c of colors) {
    if (picked.length >= n) break;
    const tooClose = picked.some((p) => colorDistance(c, p) < minDist);
    if (!tooClose) picked.push(c);
  }
  return picked;
}

export function extractPalette(body: string, count = 4): string[] {
  const seen = new Set<string>();
  const all: string[] = [];

  for (const match of body.matchAll(HEX_RE)) {
    const raw = match[0].toLowerCase();
    if (!seen.has(raw)) {
      seen.add(raw);
      all.push(raw);
    }
  }

  // Prefer interesting (saturated, mid-lightness) colors
  const interesting = all.filter(isInteresting);

  // Sort by saturation descending so the most vivid colors come first
  const sorted = interesting.sort((a, b) => {
    const ra = hexToRgb(a), rb = hexToRgb(b);
    if (!ra || !rb) return 0;
    const [, sa] = rgbToHsl(...ra);
    const [, sb] = rgbToHsl(...rb);
    return sb - sa;
  });

  const distinct = pickDistinct(sorted, count);

  // If we couldn't find enough interesting colors, pad with any hex values
  if (distinct.length < count) {
    const fallback = all.filter((c) => !distinct.includes(c));
    const extra = pickDistinct(fallback, count - distinct.length, 30);
    distinct.push(...extra);
  }

  return distinct.slice(0, count);
}
