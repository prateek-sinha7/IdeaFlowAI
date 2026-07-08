/**
 * useChatAttachments — attachment intake (picker/paste/drag-drop) with client
 * resize (UPLD-04). `resizeImage` is mocked so we can assert it is invoked for
 * images (and NOT for files) and that the resized `data`/`mime_type` land on the
 * produced attachment.
 *
 * Proves:
 *   1. `addFiles([image])` produces one image attachment routed THROUGH
 *      `resizeImage` (mock called; resized data/mime on the attachment);
 *   2. a non-image file (.pdf) is added WITHOUT resize, carrying name/mime/size;
 *   3. `onPaste` extracts a clipboard image item and routes it (same resize path);
 *   4. `onDrop` routes `dataTransfer.files` through the intake;
 *   5. the client cap rejects a disallowed type BEFORE base64 (no resize call),
 *      and rejects an over-cap image POST-resize;
 *   6. `remove(id)` drops one chip; `clear()` empties;
 *   7. every record is `retained:false` (ND-10 payload-transient).
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatAttachments } from "./useChatAttachments";
import { resizeImage } from "@/lib/resizeImage";

vi.mock("@/lib/resizeImage", () => ({
  resizeImage: vi.fn(async () => ({
    mime_type: "image/png",
    data: "QUJD", // 4 base64 chars ≈ 3 bytes — well under the cap
    width: 100,
    height: 80,
  })),
}));

const mockResize = vi.mocked(resizeImage);

function imageFile(name = "photo.png", type = "image/png"): File {
  return new File(["img-bytes"], name, { type });
}
function pdfFile(name = "doc.pdf"): File {
  return new File(["pdf-bytes"], name, { type: "application/pdf" });
}

describe("useChatAttachments", () => {
  beforeEach(() => {
    mockResize.mockClear();
    mockResize.mockResolvedValue({
      mime_type: "image/png",
      data: "QUJD",
      width: 100,
      height: 80,
    });
  });

  it("routes an image through resizeImage; resized data/mime land on the attachment", async () => {
    const { result } = renderHook(() => useChatAttachments());
    await act(async () => {
      await result.current.addFiles([imageFile()]);
    });

    expect(mockResize).toHaveBeenCalledTimes(1);
    expect(result.current.attachments).toHaveLength(1);
    const att = result.current.attachments[0];
    expect(att.kind).toBe("image");
    expect(att.data).toBe("QUJD");
    expect(att.mimeType).toBe("image/png");
    expect(att.retained).toBe(false); // ND-10 payload-transient
  });

  it("adds a non-image file WITHOUT resize, carrying name/mime/size", async () => {
    const { result } = renderHook(() => useChatAttachments());
    await act(async () => {
      await result.current.addFiles([pdfFile()]);
    });

    expect(mockResize).not.toHaveBeenCalled();
    expect(result.current.attachments).toHaveLength(1);
    const att = result.current.attachments[0];
    expect(att.kind).toBe("file");
    expect(att.name).toBe("doc.pdf");
    expect(att.mimeType).toBe("application/pdf");
    expect(att.sizeBytes).toBeGreaterThan(0);
    expect(att.retained).toBe(false);
  });

  it("onPaste extracts a clipboard image item and routes it through resize", async () => {
    const { result } = renderHook(() => useChatAttachments());
    const file = imageFile("pasted.png");
    const preventDefault = vi.fn();
    const event = {
      clipboardData: {
        items: [{ kind: "file", getAsFile: () => file }],
      },
      preventDefault,
    };

    await act(async () => {
      await result.current.onPaste(event);
    });

    expect(preventDefault).toHaveBeenCalled();
    expect(mockResize).toHaveBeenCalledTimes(1);
    expect(result.current.attachments).toHaveLength(1);
    expect(result.current.attachments[0].kind).toBe("image");
  });

  it("onDrop routes dataTransfer.files through the intake", async () => {
    const { result } = renderHook(() => useChatAttachments());
    const preventDefault = vi.fn();
    const event = {
      dataTransfer: { files: [imageFile("dropped.png")] },
      preventDefault,
    };

    await act(async () => {
      await result.current.onDrop(event);
    });

    expect(preventDefault).toHaveBeenCalled();
    expect(result.current.attachments).toHaveLength(1);
  });

  it("rejects a disallowed type BEFORE base64 (no resize), and an over-cap image after resize", async () => {
    const { result } = renderHook(() => useChatAttachments());

    // Disallowed type — rejected before any base64/resize.
    await act(async () => {
      await result.current.addFiles([
        new File(["clip"], "clip.mp4", { type: "video/mp4" }),
      ]);
    });
    expect(mockResize).not.toHaveBeenCalled();
    expect(result.current.attachments).toHaveLength(0);

    // Over-cap image — resize runs but the post-resize payload exceeds the cap.
    mockResize.mockResolvedValueOnce({
      mime_type: "image/png",
      data: "A".repeat(6_000_000), // ~4.5 MB decoded, over the ~3.75 MB cap
      width: 4000,
      height: 3000,
    });
    await act(async () => {
      await result.current.addFiles([imageFile("huge.png")]);
    });
    expect(mockResize).toHaveBeenCalledTimes(1);
    expect(result.current.attachments).toHaveLength(0);
  });

  it("remove(id) drops one chip and clear() empties the intake", async () => {
    const { result } = renderHook(() => useChatAttachments());
    await act(async () => {
      await result.current.addFiles([imageFile("a.png"), pdfFile("b.pdf")]);
    });
    expect(result.current.attachments).toHaveLength(2);

    const firstId = result.current.attachments[0].id;
    act(() => result.current.remove(firstId));
    expect(result.current.attachments).toHaveLength(1);
    expect(result.current.attachments.find((a) => a.id === firstId)).toBeUndefined();

    act(() => result.current.clear());
    expect(result.current.attachments).toHaveLength(0);
  });
});
