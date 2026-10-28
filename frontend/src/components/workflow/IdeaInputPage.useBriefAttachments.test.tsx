/**
 * `useBriefAttachments()` public contract — the attach/extract state machine
 * IdeaInputPage and ComposerPage's Simple view share (INV-3). Covers what the
 * rendered-page tests cannot observe: the size label that the hook returns but
 * the chip UI does not print, the no-token binary path, attach-order stamping of
 * staged uploads, name-keyed removal, and the composed `fileBlocks` string.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { orderedStagedUploadIds, useBriefAttachments } from "./IdeaInputPage";
import { ATTACH_MAX_CHARS } from "@/lib/constants";

const api = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => api.getToken(),
  extractFileText: (token: string, file: File) => api.extractFileText(token, file),
  stageRunFile: (token: string, file: File) => api.stageRunFile(token, file),
}));

/** A FileList stand-in: `handleFiles` only calls `Array.from(files)`. */
const asFileList = (...files: File[]) => files as unknown as FileList;

/** A File whose reported `size` is forced, so size labels need no large buffers. */
function fileWithSize(name: string, size: number, type = "application/octet-stream"): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

beforeEach(() => {
  api.getToken.mockReturnValue("test-token");
  api.extractFileText.mockResolvedValue({ filename: "doc.pdf", text: "extracted", truncated: false });
  api.stageRunFile.mockResolvedValue({ stage_id: "stage-1", files: [] });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("useBriefAttachments", () => {
  it.each([
    [1023, "1023B"],
    [1024, "1.0KB"],
    [1536, "1.5KB"],
    [1048575, "1024.0KB"],
    [1048576, "1.0MB"],
    [1572864, "1.5MB"],
  ])("labels a %i byte file as %s", (size, label) => {
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("blob.bin", size))));

    expect(result.current.attachedFiles).toEqual([{ name: "blob.bin", size: label }]);
  });

  it("adds a chip but no content block for an extension the picker does not read or stage", () => {
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("blob.bin", 10))));

    expect(result.current.attachedFileContents).toEqual([]);
    expect(result.current.fileBlocks).toBe("");
    expect(api.stageRunFile).not.toHaveBeenCalled();
  });

  it("attaches an empty content block and never calls the server when a binary document is added without a token", () => {
    api.getToken.mockReturnValue(null);
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("report.pdf", 10, "application/pdf"))));

    expect(result.current.attachedFileContents).toEqual([{ name: "report.pdf", content: "" }]);
    expect(result.current.fileBlocks).toBe("\n\n=== Attached: report.pdf ===\n\n=== End: report.pdf ===");
    expect(api.stageRunFile).not.toHaveBeenCalled();
    expect(api.extractFileText).not.toHaveBeenCalled();
  });

  it("appends the visible truncation note when the server reports a truncated extraction", async () => {
    api.extractFileText.mockResolvedValue({ filename: "big.pdf", text: "first part", truncated: true });
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("big.pdf", 10, "application/pdf"))));

    await waitFor(() => expect(result.current.attachedFileContents).toHaveLength(1));
    expect(result.current.attachedFileContents[0]).toEqual({
      name: "big.pdf",
      content: `first part\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]`,
    });
  });

  it("reads a text file client-side into the attached-block string and stages it too", async () => {
    const { result } = renderHook(() => useBriefAttachments());

    act(() =>
      result.current.handleFiles(asFileList(new File(["hello notes"], "notes.txt", { type: "text/plain" }))),
    );

    await waitFor(() => expect(result.current.attachedFileContents).toHaveLength(1));
    expect(result.current.fileBlocks).toBe("\n\n=== Attached: notes.txt ===\nhello notes\n=== End: notes.txt ===");
    // UPLD-05: the raw file must reach `.uploads/` as well, or a file-reading
    // workflow refuses the launch (422 uploads_missing) for a text-only brief.
    expect(api.stageRunFile).toHaveBeenCalledTimes(1);
    expect(api.stageRunFile).toHaveBeenCalledWith("test-token", expect.objectContaining({ name: "notes.txt" }));
    await waitFor(() =>
      expect(result.current.stagedUploads).toEqual([{ name: "notes.txt", stageId: "stage-1", attachIndex: 0 }]),
    );
    expect(result.current.uploadGate).toEqual({ kind: "ready" });
    // Text is read in the browser; only binary documents use the server preview.
    expect(api.extractFileText).not.toHaveBeenCalled();
  });

  it("gates Run while a text-only attachment is staging and opens it once the stage lands", async () => {
    const stage = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValueOnce(stage.promise);
    const { result } = renderHook(() => useBriefAttachments());

    act(() =>
      result.current.handleFiles(asFileList(new File(["# Notes"], "requirements.md", { type: "text/markdown" }))),
    );
    expect(result.current.uploadGate).toEqual({ kind: "staging", count: 1 });

    await act(async () => stage.resolve({ stage_id: "stage-md" }));

    expect(result.current.uploadGate).toEqual({ kind: "ready" });
    expect(result.current.stagedUploads).toEqual([{ name: "requirements.md", stageId: "stage-md", attachIndex: 0 }]);
  });

  it("records a text-only attachment whose stage failed and blocks Run on it", async () => {
    api.stageRunFile.mockRejectedValue(Object.assign(new Error("HTTP 413"), { name: "ApiError", status: 413 }));
    const { result } = renderHook(() => useBriefAttachments());

    act(() =>
      result.current.handleFiles(asFileList(new File(["# Notes"], "requirements.md", { type: "text/markdown" }))),
    );

    await waitFor(() => expect(result.current.uploadGate).toEqual({ kind: "failed", names: ["requirements.md"] }));
    expect(result.current.stagedUploads).toEqual([]);
  });

  it("attaches an empty block when the browser reads a text file to a null result", () => {
    // FileReader.result is null when a read yields nothing; the hook must not store "null".
    class NullResultReader {
      onload: ((ev: { target: { result: null } }) => void) | null = null;
      readAsText() {
        this.onload?.({ target: { result: null } });
      }
    }
    vi.stubGlobal("FileReader", NullResultReader);
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(new File([""], "empty.txt", { type: "text/plain" }))));

    expect(result.current.attachedFileContents).toEqual([{ name: "empty.txt", content: "" }]);
  });

  it("stamps stage ids in attach order even when the stage responses arrive reversed", async () => {
    const first = deferred<{ stage_id: string }>();
    const second = deferred<{ stage_id: string }>();
    const third = deferred<{ stage_id: string }>();
    api.stageRunFile
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
      .mockReturnValueOnce(third.promise);
    const { result } = renderHook(() => useBriefAttachments());

    // Two files in one drop, then a third in a SEPARATE attach action.
    act(() =>
      result.current.handleFiles(
        asFileList(fileWithSize("a.pdf", 1, "application/pdf"), fileWithSize("b.pdf", 1, "application/pdf")),
      ),
    );
    act(() => result.current.handleFiles(asFileList(fileWithSize("c.pdf", 1, "application/pdf"))));

    await act(async () => third.resolve({ stage_id: "stage-c" }));
    await act(async () => second.resolve({ stage_id: "stage-b" }));
    await act(async () => first.resolve({ stage_id: "stage-a" }));

    await waitFor(() => expect(result.current.stagedUploads).toHaveLength(3));
    expect(result.current.stagedUploads.map((s) => s.stageId)).toEqual(["stage-c", "stage-b", "stage-a"]);
    expect(orderedStagedUploadIds(result.current.stagedUploads)).toEqual(["stage-a", "stage-b", "stage-c"]);
  });

  it("removes a file chip together with its content block and staged upload", async () => {
    api.extractFileText.mockResolvedValue({ filename: "doc.pdf", text: "body", truncated: false });
    const { result } = renderHook(() => useBriefAttachments());
    act(() => result.current.handleFiles(asFileList(fileWithSize("doc.pdf", 1, "application/pdf"))));
    await waitFor(() => expect(result.current.stagedUploads).toHaveLength(1));
    await waitFor(() => expect(result.current.attachedFileContents).toHaveLength(1));

    act(() => result.current.removeFile(0));

    expect(result.current.attachedFiles).toEqual([]);
    expect(result.current.attachedFileContents).toEqual([]);
    expect(result.current.stagedUploads).toEqual([]);
    expect(result.current.fileBlocks).toBe("");
  });

  it("records a 413 stage as failed with the too-large reason instead of swallowing it", async () => {
    api.stageRunFile.mockRejectedValue(Object.assign(new Error("HTTP 413"), { name: "ApiError", status: 413 }));
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("big.pdf", 1, "application/pdf"))));

    await waitFor(() =>
      expect(result.current.documents[0]).toMatchObject({
        name: "big.pdf",
        status: "failed",
        reason: "File is too large for this server (limit 10 MB)",
      }),
    );
    expect(result.current.uploadGate).toEqual({ kind: "failed", names: ["big.pdf"] });
    expect(result.current.stagedUploads).toEqual([]);
  });

  it("gates Run while a document is staging and opens it once the stage lands, keeping the stagedUploads shape", async () => {
    const stage = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValueOnce(stage.promise);
    const { result } = renderHook(() => useBriefAttachments());

    act(() => result.current.handleFiles(asFileList(fileWithSize("doc.pdf", 1, "application/pdf"))));
    expect(result.current.uploadGate).toEqual({ kind: "staging", count: 1 });

    await act(async () => stage.resolve({ stage_id: "stage-doc" }));

    expect(result.current.uploadGate).toEqual({ kind: "ready" });
    expect(result.current.stagedUploads).toEqual([{ name: "doc.pdf", stageId: "stage-doc", attachIndex: 0 }]);
  });

  it("leaves every attachment in place when the removed index does not exist", () => {
    const { result } = renderHook(() => useBriefAttachments());
    act(() => result.current.handleFiles(asFileList(fileWithSize("keep.bin", 5))));

    act(() => result.current.removeFile(7));

    expect(result.current.attachedFiles.map((f) => f.name)).toEqual(["keep.bin"]);
  });

  it("removes only the image at the given index", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(async () => ({ width: 8, height: 8, close: vi.fn() })),
    );
    const { result } = renderHook(() => useBriefAttachments());
    act(() => result.current.handleFiles(asFileList(new File(["a"], "one.png", { type: "image/png" }))));
    await waitFor(() => expect(result.current.attachedImages).toHaveLength(1));
    act(() => result.current.handleFiles(asFileList(new File(["b"], "two.png", { type: "image/png" }))));
    await waitFor(() => expect(result.current.attachedImages).toHaveLength(2));

    act(() => result.current.removeImage(0));

    expect(result.current.attachedImages.map((i) => i.name)).toEqual(["two.png"]);
  });
});
