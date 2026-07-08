/**
 * UPLD-04 — client-side image downscale before base64.
 *
 * The attach flow (`IdeaInputPage`) reads an image File straight through
 * `FileReader.readAsDataURL` → base64 → the OUT-OF-BAND `images` payload (D3).
 * A single full-res phone photo can approach the server per-image cap. This
 * helper downscales oversized images on the client BEFORE base64 so uploads are
 * right-sized (better UX, fewer server rejections).
 *
 * This is a CLIENT OPTIMIZATION only — the server `_validate_images` caps remain
 * the AUTHORITATIVE trust boundary (T-30-12). The resized base64 still rides the
 * out-of-band `images` payload; it NEVER enters the brief.
 *
 * Contract:
 *  - Aspect ratio preserved; the longest edge is capped at `maxEdge`.
 *  - An image already within the bound passes through UNCHANGED (no upscaling,
 *    no needless re-encode).
 *  - png stays lossless; jpeg/webp re-encode at a bounded `quality`.
 *  - DEGRADE-NOT-BLOCK: ANY decode/canvas/encode failure resolves to the
 *    ORIGINAL file's base64 — never throws, never blocks the attach.
 */

export interface ResizeOptions {
  /** Longest-edge cap in pixels. Default 1568 — the vision model's optimal
   *  edge, which keeps a re-encoded image well under the ~3.75 MB server cap. */
  maxEdge?: number;
  /** Output mime override. Default: keep png lossless; jpeg/webp preserved;
   *  anything else re-encodes to jpeg. */
  mimeType?: string;
  /** jpeg/webp encode quality (0–1). Ignored for png. Default 0.85. */
  quality?: number;
}

export interface ResizedImage {
  /** Final mime type of `data`. */
  mime_type: string;
  /** Raw base64 — the `data:<mime>;base64,` prefix is stripped (matches the
   *  existing IdeaInputPage strip so `data` drops straight into the images
   *  payload). */
  data: string;
  /** Final pixel width (0 when the source could not be decoded / degraded). */
  width: number;
  /** Final pixel height (0 when the source could not be decoded / degraded). */
  height: number;
}

const DEFAULT_MAX_EDGE = 1568;
const DEFAULT_QUALITY = 0.85;

function stripDataUrlPrefix(dataUrl: string): string {
  return dataUrl.replace(/^data:[^;]+;base64,/, "");
}

/** Read a File to raw (prefix-stripped) base64 via FileReader — the passthrough
 *  / degrade path. */
function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(stripDataUrlPrefix((reader.result as string) ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("FileReader failed"));
    reader.readAsDataURL(file);
  });
}

interface DecodedImage {
  width: number;
  height: number;
  source: CanvasImageSource;
  close(): void;
}

/** Decode a File to a drawable source via `createImageBitmap`, falling back to
 *  an `<img>` + onload decode when the platform lacks it. */
async function decodeImage(file: File): Promise<DecodedImage> {
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    return {
      width: bitmap.width,
      height: bitmap.height,
      source: bitmap as unknown as CanvasImageSource,
      close: () => bitmap.close?.(),
    };
  }
  // Fallback: decode through an <img> element + object URL.
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("image decode failed"));
      el.src = url;
    });
    return {
      width: img.naturalWidth,
      height: img.naturalHeight,
      source: img,
      close: () => {},
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Choose the output mime: keep png lossless, preserve webp, otherwise jpeg. */
function pickOutputMime(sourceMime: string, override?: string): string {
  if (override) return override;
  if (sourceMime === "image/png") return "image/png";
  if (sourceMime === "image/webp") return "image/webp";
  return "image/jpeg";
}

export async function resizeImage(
  file: File,
  opts: ResizeOptions = {},
): Promise<ResizedImage> {
  const maxEdge = opts.maxEdge ?? DEFAULT_MAX_EDGE;
  const fallbackMime = file.type || "image/png";

  try {
    const decoded = await decodeImage(file);
    const { width: srcW, height: srcH } = decoded;

    // No upscaling: an image already within the bound passes through unchanged
    // (no needless re-encode) — return its raw passthrough base64.
    if (srcW <= maxEdge && srcH <= maxEdge) {
      decoded.close();
      const data = await fileToBase64(file);
      return { mime_type: fallbackMime, data, width: srcW, height: srcH };
    }

    // Aspect-preserving downscale so the longest edge == maxEdge.
    const scale = maxEdge / Math.max(srcW, srcH);
    const dstW = Math.max(1, Math.round(srcW * scale));
    const dstH = Math.max(1, Math.round(srcH * scale));

    const canvas = document.createElement("canvas");
    canvas.width = dstW;
    canvas.height = dstH;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no 2d canvas context");
    ctx.drawImage(decoded.source, 0, 0, dstW, dstH);
    decoded.close();

    const outMime = pickOutputMime(fallbackMime, opts.mimeType);
    const quality = opts.quality ?? DEFAULT_QUALITY;
    const dataUrl = canvas.toDataURL(outMime, quality);
    const data = stripDataUrlPrefix(dataUrl);
    // A degenerate encode (empty payload) is treated as a failure → degrade.
    if (!data) throw new Error("empty canvas encode");
    return { mime_type: outMime, data, width: dstW, height: dstH };
  } catch {
    // DEGRADE-NOT-BLOCK: resolve to the original file's base64. Never throw.
    try {
      const data = await fileToBase64(file);
      return { mime_type: fallbackMime, data, width: 0, height: 0 };
    } catch {
      return { mime_type: fallbackMime, data: "", width: 0, height: 0 };
    }
  }
}
