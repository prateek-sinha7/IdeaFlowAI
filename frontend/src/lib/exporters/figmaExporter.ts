/**
 * figmaExporter.ts
 *
 * Primary path — Playwright backend (v3 IRNode):
 *   POST /api/runs/{id}/figma-export  →  { version:3, screens:IRNode[], viewport, tokens }
 *   Full computed styles + real geometry from headless Chromium.
 *   The plugin's mapper (code.js buildTree) creates real Figma frames.
 *
 * Fallback path — client-side DOM walk (v1):
 *   When the backend returns 503/404 or runId is absent.
 *   Produces structural skeleton without computed layout.
 *
 * Both paths bundle the JSON + VelocityAI Figma plugin into one ZIP.
 */

import { ENV } from "@/lib/env";

// ─── Public surface ───────────────────────────────────────────────────────────

/**
 * Download a ZIP containing the Figma JSON + VelocityAI plugin.
 * Tries the Playwright backend first (needs runId). Falls back to the
 * client-side DOM walk when the backend is unavailable or runId is absent.
 */
export async function exportFigmaZip(
  htmlContent: string,
  filename?: string,
  runId?: string | null,
): Promise<void> {
  const stem = filename || "prototype";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let payload: any | null = null;

  // ── Attempt 1: backend Playwright extraction ─────────────────────────────
  if (runId) {
    try {
      const { authedFetch, getToken } = await import("@/lib/api");
      const token = getToken();
      console.log("[figmaExporter] calling backend for run:", runId);
      const res = await authedFetch(
        `${ENV.API_URL}/api/runs/${encodeURIComponent(runId)}/figma-export`,
        { method: "POST", headers: { "Authorization": `Bearer ${token}` } },
      );
      console.log("[figmaExporter] backend status:", res.status);
      if (res.ok) {
        payload = await res.json();
        console.log("[figmaExporter] backend returned version:", payload.version, "screens:", payload.screens?.length);
      } else {
        const body = await res.text().catch(() => "");
        console.warn("[figmaExporter] backend non-OK:", res.status, body);
        if (res.status !== 503 && res.status !== 404) {
          throw new Error(`Figma export failed (${res.status}): ${body}`);
        }
        // 503 = Playwright unavailable → fall through to client-side
      }
    } catch (err) {
      console.warn("[figmaExporter] backend failed, falling back:", err);
    }
  } else {
    console.log("[figmaExporter] no runId — using client-side DOM walk");
  }

  // ── Attempt 2: client-side DOM walk (fallback) ───────────────────────────
  if (!payload) {
    payload = htmlToFigmaJson(htmlContent, stem);
    console.log("[figmaExporter] client-side fallback, version:", payload.version);
  }

  await _bundleAndDownload(payload, stem);
}

async function _bundleAndDownload(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any,
  stem: string,
): Promise<void> {
  const json = JSON.stringify(payload, null, 2);

  // Load JSZip on demand (same pattern as FilesTab app_builder ZIP)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (!(window as any).JSZip) {
    await new Promise<void>((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("Could not load JSZip."));
      document.head.appendChild(s);
    });
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const JSZip = (window as any).JSZip;
  const zip = new JSZip();

  // 1. The prototype Figma JSON at the root of the ZIP
  zip.file(`${stem}-figma.json`, json);

  // 2. The companion plugin files fetched from /figma-plugin/ (public/)
  const pluginFiles = ["manifest.json", "code.js", "ui.html", "README.md"];
  await Promise.all(
    pluginFiles.map(async (name) => {
      try {
        const res = await fetch(`/figma-plugin/${name}`);
        if (res.ok) {
          const text = await res.text();
          zip.file(`velocityai-figma-plugin/${name}`, text);
        }
      } catch {
        // If a plugin file can't be fetched (e.g. dev env difference),
        // skip it — the JSON is still useful on its own.
      }
    }),
  );

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${stem}-figma-export.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * @deprecated Use exportFigmaZip instead.
 * Kept for any direct callers — delegates to the ZIP export.
 */
export async function exportFigmaJson(htmlContent: string, filename?: string): Promise<void> {
  return exportFigmaZip(htmlContent, filename);
}

/** Convert HTML → Figma plugin JSON (exported for unit testing). */
export function htmlToFigmaJson(htmlContent: string, name = "Prototype"): FigmaDocument {
  const dom = new DOMParser().parseFromString(htmlContent, "text/html");
  const body = dom.body;

  // Derive a page title from <title> or <h1>
  const titleEl = dom.querySelector("title");
  const h1El = dom.querySelector("h1");
  const pageTitle =
    titleEl?.textContent?.trim() ||
    h1El?.textContent?.trim() ||
    name;

  // Collect screen roots: elements explicitly marked as screens, or semantic
  // section / main / article tags, or the body itself as one screen.
  const screenRoots = collectScreenRoots(body);

  const screens: FigmaScreen[] = screenRoots.map((root, idx) => {
    const screenName =
      root.getAttribute("data-screen") ||
      root.getAttribute("aria-label") ||
      root.querySelector("h1,h2")?.textContent?.trim() ||
      `Screen ${idx + 1}`;
    return {
      name: sanitizeName(screenName),
      width: 1440,
      height: 900,
      backgroundColor: extractBgColor(root) ?? { r: 1, g: 1, b: 1, a: 1 },
      children: walkElement(root, 0),
    };
  });

  return {
    version: 1,
    document: {
      name: sanitizeName(pageTitle),
      screens,
    },
  };
}

// ─── Types (mirrored in the plugin's code.ts) ─────────────────────────────────

export interface FigmaColor {
  r: number; // 0–1
  g: number;
  b: number;
  a: number;
}

export interface FigmaTextNode {
  type: "TEXT";
  name: string;
  characters: string;
  fontSize: number;
  fontWeight: number;
  color: FigmaColor;
  italic: boolean;
  textAlign: "LEFT" | "CENTER" | "RIGHT";
}

export interface FigmaRectNode {
  type: "RECT";
  name: string;
  cornerRadius: number;
  fill: FigmaColor | null;
  stroke: FigmaColor | null;
  strokeWeight: number;
  /** Note shown as a Figma annotation (e.g. "SVG icon placeholder"). */
  note?: string;
}

export interface FigmaGroupNode {
  type: "GROUP";
  name: string;
  children: FigmaNode[];
}

export type FigmaNode = FigmaTextNode | FigmaRectNode | FigmaGroupNode;

export interface FigmaScreen {
  name: string;
  width: number;
  height: number;
  backgroundColor: FigmaColor;
  children: FigmaNode[];
}

export interface FigmaDocument {
  version: 1;
  document: {
    name: string;
    screens: FigmaScreen[];
  };
}

// ─── DOM walking ─────────────────────────────────────────────────────────────

const MAX_DEPTH = 8;
const MAX_CHILDREN_PER_NODE = 60;

function walkElement(el: Element, depth: number): FigmaNode[] {
  if (depth > MAX_DEPTH) return [];
  const nodes: FigmaNode[] = [];

  const children = Array.from(el.children).slice(0, MAX_CHILDREN_PER_NODE);
  for (const child of children) {
    const tag = child.tagName.toLowerCase();

    // ── Skip invisible / non-visual elements ─────────────────────────────
    if (["script", "style", "meta", "link", "head", "noscript", "template"].includes(tag)) {
      continue;
    }
    const style = (child as HTMLElement).style;
    if (style?.display === "none" || style?.visibility === "hidden") continue;

    // ── SVG → placeholder rect ────────────────────────────────────────────
    if (tag === "svg") {
      nodes.push({
        type: "RECT",
        name: child.getAttribute("aria-label") || "SVG icon",
        cornerRadius: 0,
        fill: { r: 0.9, g: 0.9, b: 0.9, a: 1 },
        stroke: null,
        strokeWeight: 0,
        note: "SVG icon placeholder — re-draw or replace with a Figma icon component.",
      });
      continue;
    }

    // ── IMG → placeholder rect ────────────────────────────────────────────
    if (tag === "img") {
      const altText = (child as HTMLImageElement).alt || "Image";
      nodes.push({
        type: "RECT",
        name: altText,
        cornerRadius: extractBorderRadius(child),
        fill: { r: 0.85, g: 0.85, b: 0.85, a: 1 },
        stroke: null,
        strokeWeight: 0,
        note: `Image placeholder: ${altText}`,
      });
      continue;
    }

    // ── Heading / pure text leaf ──────────────────────────────────────────
    if (["h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "label", "legend", "caption"].includes(tag)) {
      const text = (child.textContent || "").trim();
      if (text) {
        nodes.push(buildTextNode(child, tag, text));
        continue;
      }
    }

    // ── Button / anchor with text ─────────────────────────────────────────
    if (tag === "button" || tag === "a") {
      const text = (child.textContent || "").trim();
      const bgColor = extractBgColor(child);
      const group: FigmaGroupNode = {
        type: "GROUP",
        name: sanitizeName(text || tag),
        children: [],
      };
      group.children.push({
        type: "RECT",
        name: "bg",
        cornerRadius: extractBorderRadius(child),
        fill: bgColor ?? { r: 0.24, g: 0.47, b: 1, a: 1 },
        stroke: null,
        strokeWeight: 0,
      });
      if (text) {
        group.children.push({
          type: "TEXT",
          name: "label",
          characters: text,
          fontSize: extractFontSize(child, 14),
          fontWeight: 600,
          color: extractTextColor(child) ?? { r: 1, g: 1, b: 1, a: 1 },
          italic: false,
          textAlign: "CENTER",
        });
      }
      nodes.push(group);
      continue;
    }

    // ── Input / textarea / select → rectangle with label ─────────────────
    if (["input", "textarea", "select"].includes(tag)) {
      const placeholder =
        (child as HTMLInputElement).placeholder ||
        child.getAttribute("placeholder") ||
        tag;
      nodes.push({
        type: "RECT",
        name: sanitizeName(placeholder),
        cornerRadius: extractBorderRadius(child),
        fill: { r: 1, g: 1, b: 1, a: 1 },
        stroke: { r: 0.8, g: 0.8, b: 0.8, a: 1 },
        strokeWeight: 1,
        note: `Input field: ${placeholder}`,
      });
      continue;
    }

    // ── Container elements — recurse into children ────────────────────────
    const innerText = (child.textContent || "").trim();
    const childNodes = walkElement(child, depth + 1);

    // Leaf text node not covered above (e.g. <li>, <td>)
    if (childNodes.length === 0 && innerText) {
      nodes.push(buildTextNode(child, tag, innerText));
      continue;
    }

    if (childNodes.length > 0) {
      const bgColor = extractBgColor(child);
      const hasBg = bgColor !== null;
      const name = deriveGroupName(child, tag);
      if (hasBg || childNodes.length > 1) {
        const group: FigmaGroupNode = {
          type: "GROUP",
          name,
          children: hasBg
            ? [
                {
                  type: "RECT",
                  name: "bg",
                  cornerRadius: extractBorderRadius(child),
                  fill: bgColor!,
                  stroke: extractBorderColor(child),
                  strokeWeight: extractBorderWidth(child),
                },
                ...childNodes,
              ]
            : childNodes,
        };
        nodes.push(group);
      } else {
        nodes.push(...childNodes);
      }
    }
  }

  return nodes;
}

// ─── Screen root collection ───────────────────────────────────────────────────

function collectScreenRoots(body: HTMLElement): Element[] {
  // Prefer explicit data-screen markers
  const marked = Array.from(body.querySelectorAll("[data-screen]"));
  if (marked.length > 0) return marked;

  // Fall back to semantic landmarks
  const landmarks = Array.from(body.querySelectorAll("section, main, article"));
  if (landmarks.length > 0) return landmarks.slice(0, 20);

  // Last resort: treat the whole body as one screen
  return [body];
}

// ─── Node builders ────────────────────────────────────────────────────────────

function buildTextNode(el: Element, tag: string, text: string): FigmaTextNode {
  const tagFontSize: Record<string, number> = {
    h1: 36, h2: 28, h3: 22, h4: 18, h5: 16, h6: 14,
    p: 14, span: 13, label: 12, legend: 12, caption: 11,
  };
  const tagFontWeight: Record<string, number> = {
    h1: 700, h2: 700, h3: 600, h4: 600, h5: 600, h6: 600,
  };
  return {
    type: "TEXT",
    name: sanitizeName(text.slice(0, 40)),
    characters: sanitizeText(text),
    fontSize: extractFontSize(el, tagFontSize[tag] ?? 14),
    fontWeight: tagFontWeight[tag] ?? 400,
    color: extractTextColor(el) ?? { r: 0.1, g: 0.1, b: 0.1, a: 1 },
    italic: isItalic(el),
    textAlign: extractTextAlign(el),
  };
}

function deriveGroupName(el: Element, tag: string): string {
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel) return sanitizeName(ariaLabel);
  const id = el.getAttribute("id");
  if (id) return sanitizeName(id);
  const role = el.getAttribute("role");
  if (role) return `${role} (${tag})`;
  const firstText = (el.textContent || "").trim().slice(0, 30);
  if (firstText) return sanitizeName(firstText);
  return tag;
}

// ─── Style extraction helpers ─────────────────────────────────────────────────

/** Extract the resolved background color from inline style or Tailwind classes. */
function extractBgColor(el: Element): FigmaColor | null {
  const inlineStyle = (el as HTMLElement).style?.backgroundColor;
  if (inlineStyle) {
    const c = parseCssColor(inlineStyle);
    if (c) return c;
  }
  // Tailwind bg-* class hints
  const cls = el.className || "";
  return tailwindBgColor(cls);
}

function extractTextColor(el: Element): FigmaColor | null {
  const inlineStyle = (el as HTMLElement).style?.color;
  if (inlineStyle) {
    const c = parseCssColor(inlineStyle);
    if (c) return c;
  }
  const cls = el.className || "";
  return tailwindTextColor(cls);
}

function extractBorderColor(el: Element): FigmaColor | null {
  const inlineStyle = (el as HTMLElement).style?.borderColor;
  if (inlineStyle) return parseCssColor(inlineStyle);
  return null;
}

function extractBorderWidth(el: Element): number {
  const v = (el as HTMLElement).style?.borderWidth;
  if (v) return parseFloat(v) || 0;
  return 0;
}

function extractBorderRadius(el: Element): number {
  const v = (el as HTMLElement).style?.borderRadius;
  if (v) return parseFloat(v) || 0;
  // Tailwind rounded-* hints
  const cls = el.className || "";
  if (/rounded-full/.test(cls)) return 9999;
  if (/rounded-2xl/.test(cls)) return 16;
  if (/rounded-xl/.test(cls)) return 12;
  if (/rounded-lg/.test(cls)) return 8;
  if (/rounded-md/.test(cls)) return 6;
  if (/rounded-sm/.test(cls)) return 4;
  if (/rounded(?!-)/.test(cls)) return 4;
  return 0;
}

function extractFontSize(el: Element, fallback: number): number {
  const v = (el as HTMLElement).style?.fontSize;
  if (v) return parseFloat(v) || fallback;
  const cls = el.className || "";
  // Tailwind text-* size hints
  const m = cls.match(/text-(xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl)/);
  if (m) {
    const map: Record<string, number> = {
      xs: 12, sm: 14, base: 16, lg: 18, xl: 20,
      "2xl": 24, "3xl": 30, "4xl": 36, "5xl": 48, "6xl": 60,
    };
    return map[m[1]] ?? fallback;
  }
  return fallback;
}

function isItalic(el: Element): boolean {
  const v = (el as HTMLElement).style?.fontStyle;
  if (v === "italic") return true;
  return /italic/.test(el.className || "");
}

function extractTextAlign(el: Element): "LEFT" | "CENTER" | "RIGHT" {
  const v = (el as HTMLElement).style?.textAlign;
  if (v === "center") return "CENTER";
  if (v === "right") return "RIGHT";
  const cls = el.className || "";
  if (/text-center/.test(cls)) return "CENTER";
  if (/text-right/.test(cls)) return "RIGHT";
  return "LEFT";
}

// ─── CSS colour parsing ───────────────────────────────────────────────────────

function parseCssColor(value: string): FigmaColor | null {
  if (!value || value === "transparent" || value === "inherit") return null;

  // rgb(r, g, b) or rgba(r, g, b, a)
  const rgbMatch = value.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
  if (rgbMatch) {
    return {
      r: Number(rgbMatch[1]) / 255,
      g: Number(rgbMatch[2]) / 255,
      b: Number(rgbMatch[3]) / 255,
      a: rgbMatch[4] !== undefined ? Number(rgbMatch[4]) : 1,
    };
  }

  // #rrggbb or #rgb
  const hexMatch = value.match(/^#([0-9a-fA-F]{3,8})$/);
  if (hexMatch) {
    const hex = hexMatch[1];
    if (hex.length === 3) {
      return {
        r: parseInt(hex[0] + hex[0], 16) / 255,
        g: parseInt(hex[1] + hex[1], 16) / 255,
        b: parseInt(hex[2] + hex[2], 16) / 255,
        a: 1,
      };
    }
    if (hex.length === 6) {
      return {
        r: parseInt(hex.slice(0, 2), 16) / 255,
        g: parseInt(hex.slice(2, 4), 16) / 255,
        b: parseInt(hex.slice(4, 6), 16) / 255,
        a: 1,
      };
    }
    if (hex.length === 8) {
      return {
        r: parseInt(hex.slice(0, 2), 16) / 255,
        g: parseInt(hex.slice(2, 4), 16) / 255,
        b: parseInt(hex.slice(4, 6), 16) / 255,
        a: parseInt(hex.slice(6, 8), 16) / 255,
      };
    }
  }

  // Named CSS colours (small but useful subset)
  const named: Record<string, [number, number, number]> = {
    white: [255, 255, 255], black: [0, 0, 0],
    red: [255, 0, 0], green: [0, 128, 0], blue: [0, 0, 255],
    gray: [128, 128, 128], grey: [128, 128, 128],
    transparent: [0, 0, 0],
  };
  const lc = value.toLowerCase().trim();
  if (named[lc]) {
    const [r, g, b] = named[lc];
    return { r: r / 255, g: g / 255, b: b / 255, a: lc === "transparent" ? 0 : 1 };
  }

  return null;
}

// ─── Tailwind colour hints (common palette) ───────────────────────────────────

const TAILWIND_COLORS: Record<string, [number, number, number]> = {
  // slate
  "slate-50": [248, 250, 252], "slate-100": [241, 245, 249], "slate-200": [226, 232, 240],
  "slate-300": [203, 213, 225], "slate-400": [148, 163, 184], "slate-500": [100, 116, 139],
  "slate-600": [71, 85, 105],  "slate-700": [51, 65, 85],    "slate-800": [30, 41, 59],
  "slate-900": [15, 23, 42],   "slate-950": [2, 6, 23],
  // gray
  "gray-50": [249, 250, 251],  "gray-100": [243, 244, 246],  "gray-200": [229, 231, 235],
  "gray-300": [209, 213, 219], "gray-400": [156, 163, 175],  "gray-500": [107, 114, 128],
  "gray-600": [75, 85, 99],    "gray-700": [55, 65, 81],     "gray-800": [31, 41, 55],
  "gray-900": [17, 24, 39],    "gray-950": [3, 7, 18],
  // blue
  "blue-50": [239, 246, 255],  "blue-100": [219, 234, 254],  "blue-200": [191, 219, 254],
  "blue-300": [147, 197, 253], "blue-400": [96, 165, 250],   "blue-500": [59, 130, 246],
  "blue-600": [37, 99, 235],   "blue-700": [29, 78, 216],    "blue-800": [30, 64, 175],
  "blue-900": [30, 58, 138],
  // indigo
  "indigo-50": [238, 242, 255], "indigo-100": [224, 231, 255], "indigo-500": [99, 102, 241],
  "indigo-600": [79, 70, 229],  "indigo-700": [67, 56, 202],
  // violet / purple
  "violet-500": [139, 92, 246], "violet-600": [124, 58, 237],
  "purple-500": [168, 85, 247], "purple-600": [147, 51, 234],
  // pink / rose
  "pink-500": [236, 72, 153],   "rose-500": [244, 63, 94],
  // green / emerald / teal
  "green-500": [34, 197, 94],   "emerald-500": [16, 185, 129], "teal-500": [20, 184, 166],
  // yellow / amber / orange
  "yellow-400": [250, 204, 21], "amber-500": [245, 158, 11],  "orange-500": [249, 115, 22],
  // red
  "red-500": [239, 68, 68],     "red-600": [220, 38, 38],
  // neutral / white / black
  "neutral-50": [250, 250, 250], "neutral-900": [23, 23, 23],
  "white": [255, 255, 255],      "black": [0, 0, 0],
};

function tailwindBgColor(cls: string): FigmaColor | null {
  const m = cls.match(/bg-([\w-]+)/);
  if (!m) return null;
  const key = m[1];
  if (TAILWIND_COLORS[key]) {
    const [r, g, b] = TAILWIND_COLORS[key];
    return { r: r / 255, g: g / 255, b: b / 255, a: 1 };
  }
  return null;
}

function tailwindTextColor(cls: string): FigmaColor | null {
  const m = cls.match(/text-([\w-]+)/);
  if (!m) return null;
  const key = m[1];
  if (TAILWIND_COLORS[key]) {
    const [r, g, b] = TAILWIND_COLORS[key];
    return { r: r / 255, g: g / 255, b: b / 255, a: 1 };
  }
  return null;
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function sanitizeName(s: string): string {
  return s
    .replace(/[\u2018\u2019]/g, "'")   // curly single quotes → straight
    .replace(/[\u201C\u201D]/g, '"')   // curly double quotes → straight
    .replace(/\s+/g, " ")
    .replace(/[^\w\s\-–—()[\]"']/g, "")
    .trim()
    .slice(0, 60) || "Node";
}

/** Sanitize free text that ends up in JSON `characters` fields.
 *  Curly/smart quotes must become straight ASCII or JSON.parse will choke. */
function sanitizeText(s: string): string {
  return s
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"');
}

// ─── (downloadFigmaPlugin removed — the plugin is now bundled inside exportFigmaZip) ─
