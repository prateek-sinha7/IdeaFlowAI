/**
 * UPLD-04 — resizeImage unit specs.
 *
 * jsdom has no real canvas/decoder, so we mock `createImageBitmap` +
 * `HTMLCanvasElement` to drive the branches: aspect-preserving downscale,
 * no-upscale passthrough, prefix-stripped output, and graceful degrade on a
 * decode failure. The server caps stay authoritative (not tested here).
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { resizeImage } from "./resizeImage";

/** Build a File from a known base64 marker so the passthrough/degrade base64 is
 *  deterministic (FileReader.readAsDataURL round-trips it exactly). */
const MARKER = "aW1hZ2VfYnl0ZXNfbWFya2Vy"; // "image_bytes_marker"
function makeImageFile(name = "photo.png", type = "image/png"): File {
  const bytes = atob(MARKER);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new File([arr], name, { type });
}

let toDataURL: ReturnType<typeof vi.fn>;
let getContext: ReturnType<typeof vi.fn>;

beforeEach(() => {
  toDataURL = vi.fn(() => "data:image/jpeg;base64,cmVzaXplZF9ib2R5"); // "resized_body"
  getContext = vi.fn(() => ({ drawImage: vi.fn() }));
  // Mock the canvas surface jsdom does not implement.
  HTMLCanvasElement.prototype.getContext = getContext as never;
  HTMLCanvasElement.prototype.toDataURL = toDataURL as never;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("resizeImage — aspect-preserving downscale", () => {
  it("caps the longest edge at maxEdge and preserves aspect ratio", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 3000, height: 1500, close: vi.fn() })),
    );

    const result = await resizeImage(makeImageFile("big.jpg", "image/jpeg"), { maxEdge: 1568 });

    // 3000 → 1568 (scale 0.5226…); 1500 → 784 (aspect preserved).
    expect(result.width).toBe(1568);
    expect(result.height).toBe(784);
    // Re-encoded through the canvas — the prefix is stripped.
    expect(toDataURL).toHaveBeenCalledTimes(1);
    expect(result.data).toBe("cmVzaXplZF9ib2R5");
    expect(result.data).not.toMatch(/^data:/);
    // jpeg source → jpeg output (bounded quality).
    expect(result.mime_type).toBe("image/jpeg");
  });
});

describe("resizeImage — no upscale passthrough", () => {
  it("returns the original base64 unchanged when already within the bound", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 800, height: 600, close: vi.fn() })),
    );

    const result = await resizeImage(makeImageFile("small.png", "image/png"), { maxEdge: 1568 });

    // No re-encode — the canvas is never touched.
    expect(toDataURL).not.toHaveBeenCalled();
    // Passthrough of the ORIGINAL file's raw base64 (prefix-stripped).
    expect(result.data).toBe(MARKER);
    expect(result.width).toBe(800);
    expect(result.height).toBe(600);
    expect(result.mime_type).toBe("image/png");
  });
});

describe("resizeImage — degrade-not-block", () => {
  it("resolves to the original file base64 when decoding fails (never throws)", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => {
        throw new Error("decode boom");
      }),
    );

    const result = await resizeImage(makeImageFile("broken.png", "image/png"));

    // Degraded: original base64, no canvas encode, dimensions unknown (0).
    expect(toDataURL).not.toHaveBeenCalled();
    expect(result.data).toBe(MARKER);
    expect(result.width).toBe(0);
    expect(result.height).toBe(0);
    expect(result.mime_type).toBe("image/png");
  });

  it("degrades when the canvas 2d context is unavailable", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 4000, height: 4000, close: vi.fn() })),
    );
    getContext.mockReturnValue(null);

    const result = await resizeImage(makeImageFile("nocanvas.jpg", "image/jpeg"));

    expect(result.data).toBe(MARKER);
    expect(result.width).toBe(0);
    expect(result.height).toBe(0);
  });
});
