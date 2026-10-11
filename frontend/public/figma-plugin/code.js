// VelocityAI Importer — Figma Plugin (code.js)
//
// Handles two payload schemas:
//   v1 — client-side DOM walk (legacy fallback)
//        { version:1, document:{ name, screens:[{ name,width,height,backgroundColor,children }] } }
//        children: TEXT | RECT | GROUP nodes (auto-layout)
//
//   v3 — Playwright IRNode tree (production quality)
//        { version:3, screens:IRNode[], viewport:{w,h}, tokens }
//        Mapper adapted from github.com/flukelaster/claude-design-x-figma (MIT)
//        Handles: flex/grid auto-layout, absolute positioning, fills, gradients,
//                 shadows, borders, corner radii, SVG, images, rich text, opacity.
//
// The v1 path is kept for offline/dev environments where Playwright is unavailable.

figma.showUI(__html__, { width: 480, height: 560, title: "VelocityAI Importer" });

figma.ui.onmessage = async (msg) => {
  if (msg.type === "import") {
    try {
      const doc = msg.payload;
      validatePayload(doc);
      await buildDocument(doc);
      const count = doc.version === 3 ? doc.screens.length : doc.document.screens.length;
      figma.notify("\u2705 Imported " + count + " screen(s) successfully.");
      figma.closePlugin();
    } catch (err) {
      figma.ui.postMessage({ type: "error", message: String(err) });
    }
  }
  if (msg.type === "cancel") figma.closePlugin();
};

// ─── Validation ───────────────────────────────────────────────────────────────

function validatePayload(doc) {
  if (!doc || typeof doc !== "object") throw new Error("Invalid payload: not an object.");
  if (doc.version !== 1 && doc.version !== 2 && doc.version !== 3)
    throw new Error("Unsupported file version: " + doc.version + ". Export a fresh file from VelocityAI.");
  if (doc.version === 3) {
    if (!Array.isArray(doc.screens)) throw new Error("Payload missing screens array.");
    if (doc.screens.length === 0) throw new Error("No screens found in the payload.");
    if (doc.screens.length > 50) throw new Error("Too many screens (" + doc.screens.length + "). Max 50.");
  } else {
    if (!doc.document || !Array.isArray(doc.document.screens))
      throw new Error("Payload missing document.screens array.");
    if (doc.document.screens.length === 0) throw new Error("No screens found in the payload.");
  }
}

// ─── Document entry point ─────────────────────────────────────────────────────

async function buildDocument(doc) {
  const page = figma.currentPage;
  if (doc.version === 3) {
    page.name = (doc.screens[0] && doc.screens[0].attrs && doc.screens[0].attrs.title)
      || "VelocityAI Import";
    await loadFontsForIR(doc.screens);
    const GAP = 80;
    let xOffset = 0;
    const vw = (doc.viewport && doc.viewport.w) || 1440;
    const vh = (doc.viewport && doc.viewport.h) || 900;
    for (const screen of doc.screens) {
      const frame = await buildScreenV3(screen, xOffset, vw, vh);
      page.appendChild(frame);
      xOffset += vw + GAP;
    }
  } else {
    page.name = doc.document.name || "VelocityAI Import";
    await loadFontsV1();
    const GAP = 80;
    let xOffset = 0;
    for (const screen of doc.document.screens) {
      const frame = buildScreenV1(screen, xOffset);
      page.appendChild(frame);
      xOffset += screen.width + GAP;
    }
  }
  figma.viewport.scrollAndZoomIntoView(page.children);
}

// ═══════════════════════════════════════════════════════════════════════════════
// V3 PATH — IRNode mapper (adapted from flukelaster/claude-design-x-figma, MIT)
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Font loading for v3 ─────────────────────────────────────────────────────

const _loadedFonts = new Set(); // "Family|Style"

async function ensureFont(family, style) {
  const key = family + "|" + style;
  if (_loadedFonts.has(key)) return;
  try { await figma.loadFontAsync({ family, style }); _loadedFonts.add(key); }
  catch { /* unavailable — caller falls back to Inter Regular */ }
}

async function loadFontsForIR(screens) {
  // Always load Inter as the baseline
  await ensureFont("Inter", "Regular");
  await ensureFont("Inter", "Medium");
  await ensureFont("Inter", "Semi Bold");
  await ensureFont("Inter", "Bold");
  // Collect all font families from the IR tree
  const families = new Set();
  function collectFamilies(node) {
    if (!node) return;
    const c = node.computed;
    if (c && c.fontFamily) {
      const first = c.fontFamily.split(",")[0].replace(/['"]/g, "").trim();
      if (first) families.add(first);
    }
    if (Array.isArray(node.children)) node.children.forEach(collectFamilies);
  }
  screens.forEach(collectFamilies);
  for (const fam of families) {
    if (fam === "Inter") continue;
    await ensureFont(fam, "Regular");
    await ensureFont(fam, "Bold");
  }
}

// ─── Screen builder (v3) ─────────────────────────────────────────────────────

async function buildScreenV3(irNode, xOffset, vw, vh) {
  const frame = figma.createFrame();
  // Use the nav label captured during click-through, or fall back to the tag name
  frame.name = irNode._nav_label || irNode.tag || "Screen";
  frame.resize(vw, vh);
  frame.x = xOffset;
  frame.y = 0;
  frame.clipsContent = true;
  frame.layoutMode = "NONE";

  // ── Background ────────────────────────────────────────────────────────────
  // Priority 1: use the screenshot as background fill — it guarantees the
  // screen always looks like the HTML prototype, even for complex gradients,
  // CSS grid patterns and JS-rendered charts that the mapper can't reproduce.
  // Editable layers are built on top so designers can still edit text/components.
  const screenshotSrc = irNode._screenshot;
  if (screenshotSrc) {
    try {
      const bytes = await fetchImageBytes(screenshotSrc);
      if (bytes) {
        const img = figma.createImage(bytes);
        frame.fills = [{ type: "IMAGE", scaleMode: "FILL", imageHash: img.hash }];
      }
    } catch {
      // Screenshot embed failed — fall through to CSS background below
    }
  }

  // If no screenshot, use the CSS background color
  if (!screenshotSrc || frame.fills.length === 0) {
    const bgColor = irNode.computed && irNode.computed.backgroundColor;
    if (bgColor && bgColor !== "rgba(0, 0, 0, 0)") {
      const paint = cssColorToSolid(bgColor);
      if (paint) frame.fills = [paint];
      else frame.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
    } else {
      frame.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
    }
  }

  // Build editable children on top of the background
  for (const child of (irNode.children || [])) {
    const node = await buildNodeV3(child, irNode);
    if (node) frame.appendChild(node);
  }

  return frame;
}

// ─── Node dispatcher (v3) ────────────────────────────────────────────────────

async function buildNodeV3(ir, parent) {
  if (!ir) return null;
  const c = ir.computed || {};

  // Skip invisible nodes
  if (c.display === "none") return null;
  if (typeof c.opacity === "number" && c.opacity === 0) return null;

  const tag = ir.tag;

  // SVG — use figma.createNodeFromSvg for real vectors
  if (tag === "svg") return buildSvgV3(ir);

  // IMG
  if (tag === "img") return buildImageV3(ir);

  // Pure text node
  if (tag === "#text") return buildTextNodeV3(ir, parent);

  // Text leaf (element with only text content + no container styling)
  if (isTextLeaf(ir)) return buildTextLeafV3(ir, parent);

  // Container — frame with auto-layout or absolute children
  return buildFrameV3(ir, parent);
}

// ─── SVG (v3) ────────────────────────────────────────────────────────────────

function buildSvgV3(ir) {
  const svgStr = ir.attrs && ir.attrs.__svg;
  if (!svgStr) return null;
  const c = ir.computed || {};
  const cur = c.color;
  const svg = (cur && cur !== "rgb(0, 0, 0)")
    ? svgStr.replace(/currentColor/gi, cur)
    : svgStr;
  try {
    const node = figma.createNodeFromSvg(svg);
    node.name = "svg";
    if (c.rectW && c.rectH) {
      try { node.resize(Math.max(1, c.rectW), Math.max(1, c.rectH)); } catch {}
    }
    // No positioning here: buildSvgV3 takes no parent, and buildFrameV3 already
    // places every child from its own computed rect after appendChild.
    return node;
  } catch {
    // SVG parse failed — fallback rectangle
    return buildFallbackRect(ir, "SVG (parse failed)");
  }
}

// ─── Image (v3) ──────────────────────────────────────────────────────────────

async function buildImageV3(ir) {
  const c = ir.computed || {};
  const rect = figma.createRectangle();
  rect.name = (ir.attrs && ir.attrs.alt) || "Image";
  const w = Math.max(c.rectW || c.width || 100, 1);
  const h = Math.max(c.rectH || c.height || 100, 1);
  rect.resize(w, h);
  if (c.borderTopLeftRadius) rect.cornerRadius = c.borderTopLeftRadius;

  const src = ir.attrs && ir.attrs.src;
  if (src) {
    try {
      const bytes = await fetchImageBytes(src);
      if (bytes) {
        const img = figma.createImage(bytes);
        rect.fills = [{ type: "IMAGE", scaleMode: "FILL", imageHash: img.hash }];
        return rect;
      }
    } catch {}
  }
  rect.fills = [{ type: "SOLID", color: { r: 0.85, g: 0.85, b: 0.85 }, opacity: 1 }];
  return rect;
}

// ─── Text nodes (v3) ─────────────────────────────────────────────────────────

async function buildTextNodeV3(ir, parent) {
  const text = (ir.text || "").replace(/\n$/, "").trim();
  if (!text) return null;
  const c = ir.computed || {};
  const pcs = parent && parent.computed;
  // Inherit from parent for raw text nodes
  const fontSize = c.fontSize || (pcs && pcs.fontSize) || 14;
  const fontWeight = c.fontWeight || (pcs && pcs.fontWeight) || 400;
  const fontFamily = cleanFamily(c.fontFamily || (pcs && pcs.fontFamily) || "Inter");
  const color = c.color || (pcs && pcs.color) || "rgb(0,0,0)";

  const t = figma.createText();
  const fontName = await resolveFont(fontFamily, fontWeight);
  t.fontName = fontName;
  t.fontSize = Math.max(fontSize, 6);
  t.characters = text;
  const fill = cssColorToSolid(color);
  if (fill) t.fills = [fill];
  t.textAlignHorizontal = cssAlignToFigma(c.textAlign || (pcs && pcs.textAlign));
  t.name = text.slice(0, 40);
  try { t.textAutoResize = "WIDTH_AND_HEIGHT"; } catch {}
  return t;
}

async function buildTextLeafV3(ir, _parent) {
  const text = joinText(ir).trim();
  if (!text) return null;
  const c = ir.computed || {};
  const fontSize = c.fontSize || 14;
  const fontWeight = c.fontWeight || 400;
  const fontFamily = cleanFamily(c.fontFamily || "Inter");
  const color = c.color || "rgb(0,0,0)";

  const t = figma.createText();
  const fontName = await resolveFont(fontFamily, fontWeight);
  t.fontName = fontName;
  t.fontSize = Math.max(fontSize, 6);
  t.characters = text;
  const fill = cssColorToSolid(color);
  if (fill) t.fills = [fill];
  if (c.lineHeight) { try { t.lineHeight = { value: c.lineHeight, unit: "PIXELS" }; } catch {} }
  if (c.letterSpacing) { try { t.letterSpacing = { value: c.letterSpacing, unit: "PIXELS" }; } catch {} }
  t.textAlignHorizontal = cssAlignToFigma(c.textAlign);
  t.name = text.slice(0, 40);

  const measuredW = c.rectW || 0;
  const measuredH = c.rectH || 0;
  const lh = c.lineHeight || fontSize || 16;
  const isMultiline = measuredH > lh * 1.5;
  if (measuredW > 0 && isMultiline) {
    // Multi-line: fix width to match browser wrap, let height grow.
    try { t.textAutoResize = "HEIGHT"; } catch {}
    try { t.resize(Math.max(measuredW, 1), t.height); } catch {}
  } else if (measuredW > 0) {
    // Single-line: auto-size both axes — Figma's metrics differ slightly from
    // Chrome's, so fixing width causes clipping. Let Figma size it naturally.
    try { t.textAutoResize = "WIDTH_AND_HEIGHT"; } catch {}
  } else {
    try { t.textAutoResize = "WIDTH_AND_HEIGHT"; } catch {}
  }
  return t;
}

// ─── Container frame (v3) ────────────────────────────────────────────────────

async function buildFrameV3(ir, _parent) {
  const c = ir.computed || {};
  const frame = figma.createFrame();
  frame.name = ir.tag || "Frame";

  const w = Math.max(c.rectW || c.width || 100, 1);
  const h = Math.max(c.rectH || c.height || 100, 1);
  frame.resize(w, h);

  // ── Fills ─────────────────────────────────────────────────────────────
  const fills = [];
  const bg = c.backgroundColor;
  if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") {
    const p = cssColorToSolid(bg);
    if (p) fills.push(p);
  }
  // Background image / gradient
  const bgImg = c.backgroundImage;
  if (bgImg && bgImg !== "none") {
    if (/^url\(/.test(bgImg)) {
      const urlMatch = bgImg.match(/url\(\s*["']?([^"')]+)["']?\s*\)/);
      if (urlMatch) {
        try {
          const bytes = await fetchImageBytes(urlMatch[1]);
          if (bytes) {
            const img = figma.createImage(bytes);
            fills.push({ type: "IMAGE", scaleMode: "FILL", imageHash: img.hash });
          }
        } catch {}
      }
    } else {
      const grad = parseGradient(bgImg);
      if (grad) fills.push(grad);
    }
  }
  frame.fills = fills.length > 0 ? fills : [];

  // ── Corner radius ─────────────────────────────────────────────────────
  const tl = c.borderTopLeftRadius || 0;
  const tr = c.borderTopRightRadius || 0;
  const bl = c.borderBottomLeftRadius || 0;
  const br = c.borderBottomRightRadius || 0;
  if (tl === tr && tr === bl && bl === br) {
    frame.cornerRadius = tl;
  } else {
    try {
      frame.topLeftRadius = tl; frame.topRightRadius = tr;
      frame.bottomLeftRadius = bl; frame.bottomRightRadius = br;
    } catch { frame.cornerRadius = tl; }
  }

  // ── Stroke / border ───────────────────────────────────────────────────
  const bw = Math.max(c.borderTopWidth || 0, c.borderRightWidth || 0,
    c.borderBottomWidth || 0, c.borderLeftWidth || 0);
  if (bw > 0) {
    const bc = c.borderColor || c.borderTopColor || c.borderRightColor || "#E5E7EB";
    const strokePaint = cssColorToSolid(bc);
    if (strokePaint) {
      frame.strokes = [strokePaint];
      frame.strokeWeight = bw;
      frame.strokeAlign = "INSIDE";
    }
  }

  // ── Shadows ───────────────────────────────────────────────────────────
  if (c.boxShadow && c.boxShadow !== "none") {
    const shadows = parseBoxShadow(c.boxShadow);
    if (shadows.length) frame.effects = shadows;
  }

  // ── Opacity ───────────────────────────────────────────────────────────
  if (typeof c.opacity === "number" && c.opacity < 1) frame.opacity = c.opacity;

  // ── Overflow clip ─────────────────────────────────────────────────────
  frame.clipsContent = !!(c.overflow && c.overflow !== "visible");

  // ── Layout: absolute positioning (pixel-perfect fidelity) ─────────────
  // Using NONE layout so every child is placed by its computed bounding rect.
  frame.layoutMode = "NONE";

  // Build children — absolute positioned relative to this frame's origin
  for (const child of (ir.children || [])) {
    const childNode = await buildNodeV3(child, ir);
    if (!childNode) continue;
    frame.appendChild(childNode);
    // Place child relative to this frame's origin using computed rects
    if (child.computed && c.rectX !== undefined) {
      childNode.x = Math.round((child.computed.rectX || 0) - (c.rectX || 0));
      childNode.y = Math.round((child.computed.rectY || 0) - (c.rectY || 0));
    }
  }

  return frame;
}

// ─── Fallback rectangle ───────────────────────────────────────────────────────

function buildFallbackRect(ir, label) {
  const c = ir.computed || {};
  const rect = figma.createRectangle();
  rect.name = label || ir.tag || "Placeholder";
  rect.resize(Math.max(c.rectW || 40, 1), Math.max(c.rectH || 20, 1));
  rect.fills = [{ type: "SOLID", color: { r: 0.9, g: 0.9, b: 0.9 } }];
  return rect;
}

// ─── Helpers: text ───────────────────────────────────────────────────────────

// Only INLINE_TAGS is consulted (by isTextLeaf). The tag/style lists that used to
// sit beside it were unreferenced, so they are not carried here.
const INLINE_TAGS = new Set(["span","strong","em","a","b","i","small","sup","sub","mark","u","code"]);

function hasContainerStyling(ir) {
  const c = ir.computed;
  if (!c) return false;
  if (c.backgroundColor && c.backgroundColor !== "rgba(0, 0, 0, 0)") return true;
  if (c.backgroundImage && c.backgroundImage !== "none") return true;
  if ((c.borderTopWidth || 0) > 0) return true;
  if ((c.borderTopLeftRadius || 0) > 0) return true;
  if (c.boxShadow && c.boxShadow !== "none") return true;
  return false;
}

function isTextLeaf(ir) {
  if (ir.tag === "#text") return true;
  if (hasContainerStyling(ir)) return false;
  if (ir.children.length === 0 && ir.text) return true;
  if (ir.children.every(c => c.tag === "#text")) return true;
  if (ir.children.every(c => c.tag === "#text" || INLINE_TAGS.has(c.tag))) return true;
  return false;
}

function joinText(ir) {
  if (ir.tag === "#text") return ir.text || "";
  if (ir.text && ir.children.length === 0) return ir.text;
  return ir.children.map(joinText).join("");
}

function cleanFamily(css) {
  if (!css) return "Inter";
  return css.split(",")[0].replace(/['"]/g, "").trim() || "Inter";
}

function cssAlignToFigma(align) {
  if (!align) return "LEFT";
  if (align.includes("center")) return "CENTER";
  if (align.includes("right")) return "RIGHT";
  if (align.includes("justify")) return "JUSTIFIED";
  return "LEFT";
}

// ─── Helpers: fonts ───────────────────────────────────────────────────────────

function weightToStyle(w) {
  if (w >= 850) return "Black";
  if (w >= 750) return "ExtraBold";
  if (w >= 650) return "Bold";
  if (w >= 550) return "SemiBold";
  if (w >= 450) return "Medium";
  return "Regular";
}

async function resolveFont(family, weight) {
  const style = weightToStyle(weight || 400);
  // Exact match
  const exactKey = family + "|" + style;
  if (_loadedFonts.has(exactKey)) return { family, style };
  // Try to load
  try {
    await figma.loadFontAsync({ family, style });
    _loadedFonts.add(exactKey);
    return { family, style };
  } catch {}
  // Try Semi Bold alias
  if (style === "SemiBold") {
    try {
      await figma.loadFontAsync({ family, style: "Semi Bold" });
      _loadedFonts.add(family + "|Semi Bold");
      return { family, style: "Semi Bold" };
    } catch {}
  }
  // Fall back to Inter Regular
  return { family: "Inter", style: "Regular" };
}

// ─── Helpers: colors ──────────────────────────────────────────────────────────

function cssColorToSolid(css) {
  if (!css || css === "transparent" || css === "none") return null;
  const rgba = css.match(/rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)/);
  if (rgba) {
    const a = rgba[4] !== undefined ? parseFloat(rgba[4]) : 1;
    if (a < 0.02) return null; // near-transparent
    return { type: "SOLID", color: { r: +rgba[1]/255, g: +rgba[2]/255, b: +rgba[3]/255 }, opacity: a };
  }
  const hex = css.match(/^#([0-9a-fA-F]{3,8})$/);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    if (h.length === 6) return { type: "SOLID", color: { r: parseInt(h.slice(0,2),16)/255, g: parseInt(h.slice(2,4),16)/255, b: parseInt(h.slice(4,6),16)/255 }, opacity: 1 };
    if (h.length === 8) return { type: "SOLID", color: { r: parseInt(h.slice(0,2),16)/255, g: parseInt(h.slice(2,4),16)/255, b: parseInt(h.slice(4,6),16)/255 }, opacity: parseInt(h.slice(6,8),16)/255 };
  }
  return null;
}

// ─── Helpers: gradients ───────────────────────────────────────────────────────

function parseGradient(css) {
  if (!css) return null;
  const isLinear = css.startsWith("linear-gradient");
  const isRadial = css.startsWith("radial-gradient");
  if (!isLinear && !isRadial) return null;

  // Extract colour stops — simplified but handles common cases
  const inner = css.replace(/^(?:linear|radial)-gradient\(\s*/,"").replace(/\)\s*$/,"");
  const parts = splitGradientParts(inner);

  const stops = [];
  let angleRad = Math.PI; // default: top→bottom = 180deg
  let foundAngle = false;

  for (let i = 0; i < parts.length; i++) {
    const p = parts[i].trim();
    // Angle token
    if (!foundAngle && /^[\d.-]+deg$/.test(p)) {
      const deg = parseFloat(p);
      angleRad = (deg - 90) * Math.PI / 180;
      foundAngle = true;
      continue;
    }
    if (!foundAngle && /^to\s/.test(p)) {
      const dir = p.replace("to ", "").trim();
      if (dir === "bottom") angleRad = Math.PI;
      else if (dir === "top") angleRad = 0;
      else if (dir === "right") angleRad = Math.PI / 2;
      else if (dir === "left") angleRad = -Math.PI / 2;
      foundAngle = true;
      continue;
    }
    // Colour stop: "color [position]"
    const stopMatch = p.match(/^(.+?)\s+([\d.]+%?)$/);
    const colorStr = stopMatch ? stopMatch[1].trim() : p.trim();
    const posStr = stopMatch ? stopMatch[2].trim() : null;
    const paint = cssColorToSolid(colorStr);
    if (!paint) continue;
    let pos = posStr ? (parseFloat(posStr) / 100) : (stops.length === 0 ? 0 : 1);
    pos = Math.max(0, Math.min(1, pos));
    stops.push({ position: pos, color: { ...paint.color, a: paint.opacity || 1 } });
  }

  if (stops.length < 2) return null;
  // Ensure stops are sorted and span 0–1
  stops.sort((a, b) => a.position - b.position);
  if (stops[0].position > 0) stops[0].position = 0;
  if (stops[stops.length-1].position < 1) stops[stops.length-1].position = 1;

  const cos = Math.cos(angleRad), sin = Math.sin(angleRad);
  return {
    type: "GRADIENT_LINEAR",
    gradientStops: stops,
    gradientTransform: [[cos, -sin, (1 - cos + sin) / 2], [sin, cos, (1 - cos - sin) / 2]],
  };
}

function splitGradientParts(s) {
  const parts = [];
  let depth = 0, start = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")") depth--;
    else if (s[i] === "," && depth === 0) {
      parts.push(s.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(s.slice(start));
  return parts;
}

// ─── Helpers: box-shadow ──────────────────────────────────────────────────────

function parseBoxShadow(css) {
  if (!css || css === "none") return [];
  const effects = [];
  // Split on commas that are not inside rgb/rgba parens
  const shadows = splitGradientParts(css);
  for (const shadow of shadows) {
    const s = shadow.trim();
    const inset = s.startsWith("inset");
    const clean = inset ? s.replace(/^inset\s+/, "") : s;
    // Extract colour (last token that looks like a colour)
    const rgbaMatch = clean.match(/rgba?\([^)]+\)/);
    const hexMatch = clean.match(/#[0-9a-fA-F]{3,8}/);
    const colorStr = (rgbaMatch && rgbaMatch[0]) || (hexMatch && hexMatch[0]) || "rgba(0,0,0,0.2)";
    const remaining = clean.replace(colorStr, "").trim();
    const nums = remaining.match(/-?[\d.]+(?:px)?/g) || [];
    const x = parseFloat(nums[0] || "0");
    const y = parseFloat(nums[1] || "0");
    const blur = parseFloat(nums[2] || "0");
    const spread = parseFloat(nums[3] || "0");
    const paint = cssColorToSolid(colorStr);
    if (!paint) continue;
    effects.push({
      type: inset ? "INNER_SHADOW" : "DROP_SHADOW",
      color: { ...paint.color, a: paint.opacity || 0.2 },
      offset: { x, y },
      radius: Math.max(0, blur),
      spread: spread,
      visible: true,
      blendMode: "NORMAL",
      showShadowBehindNode: !inset,
    });
  }
  return effects;
}

// ─── Helpers: image fetch ─────────────────────────────────────────────────────

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const B64_LOOKUP = (() => { const a = new Uint8Array(256); for (let i = 0; i < B64.length; i++) a[B64.charCodeAt(i)] = i; return a; })();

function b64decode(input) {
  let data = input.replace(/[^A-Za-z0-9+/]/g, "");
  const pad = data.length % 4;
  if (pad) data += "=".repeat(4 - pad);
  const len = (data.length / 4) * 3 - (data.endsWith("==") ? 2 : data.endsWith("=") ? 1 : 0);
  const bytes = new Uint8Array(len);
  let p = 0;
  for (let i = 0; i < data.length; i += 4) {
    const a = B64_LOOKUP[data.charCodeAt(i)], b = B64_LOOKUP[data.charCodeAt(i+1)];
    const c2 = B64_LOOKUP[data.charCodeAt(i+2)], d = B64_LOOKUP[data.charCodeAt(i+3)];
    if (p < len) bytes[p++] = (a << 2) | (b >> 4);
    if (p < len) bytes[p++] = ((b & 15) << 4) | (c2 >> 2);
    if (p < len) bytes[p++] = ((c2 & 3) << 6) | d;
  }
  return bytes;
}

async function fetchImageBytes(src) {
  if (!src) return null;
  if (src.startsWith("data:")) {
    const comma = src.indexOf(",");
    const meta = src.slice(5, comma);
    const data = src.slice(comma + 1);
    if (meta.includes("base64")) return b64decode(data);
    return null;
  }
  try {
    const res = await fetch(src);
    const buf = await res.arrayBuffer();
    return new Uint8Array(buf);
  } catch { return null; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// V1 PATH — legacy client-side DOM walk (auto-layout)
// ═══════════════════════════════════════════════════════════════════════════════

const FONT_FAMILY_V1 = "Inter";
const FONT_STYLES_V1 = ["Regular", "Medium", "Semi Bold", "Bold"];
const _loadedV1 = new Set();

async function loadFontsV1() {
  for (const style of FONT_STYLES_V1) {
    try {
      await figma.loadFontAsync({ family: FONT_FAMILY_V1, style });
      _loadedV1.add(style);
    } catch {}
  }
  if (!_loadedV1.has("Regular")) throw new Error("Could not load Inter Regular. Make sure Inter is installed.");
}

function resolveWeightV1(w) {
  if (w >= 700) return "Bold";
  if (w >= 600) return "Semi Bold";
  if (w >= 500) return "Medium";
  return "Regular";
}

function buildScreenV1(screen, xOffset) {
  const frame = figma.createFrame();
  frame.name = screen.name || "Screen";
  frame.resize(screen.width || 1440, screen.height || 900);
  frame.x = xOffset; frame.y = 0;
  frame.clipsContent = true;
  const bg = screen.backgroundColor;
  frame.fills = bg ? [{ type: "SOLID", color: toRgb(bg), opacity: bg.a ?? 1 }]
    : [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
  frame.layoutMode = "VERTICAL";
  frame.primaryAxisSizingMode = "FIXED";
  frame.counterAxisSizingMode = "FIXED";
  frame.paddingTop = 24; frame.paddingBottom = 24;
  frame.paddingLeft = 24; frame.paddingRight = 24;
  frame.itemSpacing = 12;
  appendChildrenV1(frame, screen.children || []);
  return frame;
}

function appendChildrenV1(parent, childDefs) {
  for (const def of childDefs) {
    const node = buildNodeV1(def);
    if (!node) continue;
    parent.appendChild(node);
    try { node.layoutSizingHorizontal = "FILL"; } catch {}
  }
}

function buildNodeV1(def) {
  if (!def || !def.type) return null;
  switch (def.type) {
    case "TEXT": return buildTextV1(def);
    case "RECT": return buildRectV1(def);
    case "GROUP": return buildGroupV1(def);
    default: return null;
  }
}

function buildTextV1(def) {
  const t = figma.createText();
  t.name = def.name || "Text";
  const desired = resolveWeightV1(def.fontWeight ?? 400);
  const style = _loadedV1.has(desired) ? desired : "Regular";
  t.fontName = { family: FONT_FAMILY_V1, style };
  t.fontSize = Math.max(def.fontSize ?? 14, 6);
  t.characters = def.characters || "";
  const c = def.color ?? { r: 0.1, g: 0.1, b: 0.1, a: 1 };
  t.fills = [{ type: "SOLID", color: toRgb(c), opacity: c.a ?? 1 }];
  const alignMap = { LEFT: "LEFT", CENTER: "CENTER", RIGHT: "RIGHT" };
  t.textAlignHorizontal = alignMap[def.textAlign] || "LEFT";
  return t;
}

function buildRectV1(def) {
  const rect = figma.createRectangle();
  rect.name = def.name || "Rectangle";
  rect.resize(200, 40);
  rect.fills = def.fill ? [{ type: "SOLID", color: toRgb(def.fill), opacity: def.fill.a ?? 1 }] : [];
  if (def.stroke && (def.strokeWeight ?? 0) > 0) {
    rect.strokes = [{ type: "SOLID", color: toRgb(def.stroke), opacity: def.stroke.a ?? 1 }];
    rect.strokeWeight = def.strokeWeight; rect.strokeAlign = "INSIDE";
  }
  rect.cornerRadius = Math.min(def.cornerRadius ?? 0, 9999);
  if (def.note) { rect.setPluginData("velocityai_note", def.note); rect.name += " [\u24d8]"; }
  return rect;
}

function buildGroupV1(def) {
  const frame = figma.createFrame();
  frame.name = def.name || "Group";
  frame.fills = [];
  frame.layoutMode = "VERTICAL";
  frame.primaryAxisSizingMode = "AUTO"; frame.counterAxisSizingMode = "AUTO";
  frame.itemSpacing = 8;
  frame.paddingTop = 8; frame.paddingBottom = 8;
  frame.paddingLeft = 12; frame.paddingRight = 12;
  frame.clipsContent = false;
  appendChildrenV1(frame, def.children || []);
  return frame;
}

function toRgb(color) {
  return { r: clamp(color.r ?? 0), g: clamp(color.g ?? 0), b: clamp(color.b ?? 0) };
}
function clamp(v, lo = 0, hi = 1) { return Math.max(lo, Math.min(hi, v)); }
