import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * SC-1 / D-15 regression guard for the run-screen TOKEN LAYER.
 *
 * Asserts the canonical Hexaware palette + Manrope/Heebo fonts are PRESENT and
 * the retired values (#2563eb, Inter, Fraunces, JetBrains) are ABSENT — proving
 * there is no per-page palette fork and the old palette is gone from the token
 * layer. Comment lines are stripped before the ABSENT assertions so header prose
 * can never self-invalidate the guard.
 *
 * The per-consumer "no new raw hex in the run subtree" checks live in the
 * downstream consumer plans (06/07/08/09); this file guards the token layer only.
 */

const GLOBALS_PATH = resolve(__dirname, "../globals.css");
const LAYOUT_PATH = resolve(__dirname, "../../app/layout.tsx");

const globals = readFileSync(GLOBALS_PATH, "utf8");
const layout = readFileSync(LAYOUT_PATH, "utf8");

/** Strip full-line CSS comments (`/* ... *\/` on their own line) and inline
 *  trailing comments so retired tokens can never hide inside prose. */
function stripCssComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

const globalsCode = stripCssComments(globals);

describe("run-screen token layer — canonical palette PRESENT", () => {
  it("declares the one-chroma brand #3C2CDA", () => {
    expect(globals).toContain("#3C2CDA");
  });

  it("declares the full status ramp (green/red/amber/neutral)", () => {
    for (const hex of ["#1F7A4D", "#A33A32", "#9A6B1E", "#9A9B92"]) {
      expect(globals).toContain(hex);
    }
  });

  it("declares the resolved radius ladder (button=10, card=14)", () => {
    expect(globals).toContain("--radius-button: 10px");
    expect(globals).toContain("--radius-card: 14px");
  });

  it("binds the sans/serif slots to the next/font CSS variables", () => {
    expect(globals).toMatch(/--font-sans:\s*var\(--font-manrope\)/);
    expect(globals).toMatch(/--font-serif:\s*var\(--font-heebo\)/);
  });
});

describe("run-screen token layer — retired palette ABSENT", () => {
  it("has no retired blue accent (#2563eb) outside comments", () => {
    expect(globalsCode.toLowerCase()).not.toContain("2563eb");
  });

  it("has no retired background (#f5f5f0) outside comments", () => {
    expect(globalsCode.toLowerCase()).not.toContain("f5f5f0");
  });

  it("has no retired font references (Inter/Fraunces/JetBrains) outside comments", () => {
    const lower = globalsCode.toLowerCase();
    expect(lower).not.toContain("font-inter");
    expect(lower).not.toContain("font-fraunces");
    expect(lower).not.toContain("jetbrains");
  });
});

describe("layout font loaders — Manrope + Heebo wired, Inter/Fraunces gone", () => {
  it("imports and exposes Manrope + Heebo as CSS variables", () => {
    expect(layout).toMatch(/Manrope/);
    expect(layout).toMatch(/Heebo/);
    expect(layout).toContain("--font-manrope");
    expect(layout).toContain("--font-heebo");
  });

  it("no longer references Inter or Fraunces", () => {
    expect(layout).not.toMatch(/\bInter\b/);
    expect(layout).not.toContain("Fraunces");
  });
});
