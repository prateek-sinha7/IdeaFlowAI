/**
 * useStagedDocuments — per-document staging state for the launch surfaces.
 * Boundary: `stageRunFile` (@/lib/api), driven with hand-held deferreds so
 * resolution order is deterministic (no timers, no sleeps).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { UPLOAD_FAILED_MESSAGE, UPLOAD_TOO_LARGE_MESSAGE } from "@/lib/uploadErrors";
import { uploadGateFor, uploadGateMessage, useStagedDocuments } from "./useStagedDocuments";

const api = vi.hoisted(() => ({ stageRunFile: vi.fn() }));

vi.mock("@/lib/api", () => ({
  stageRunFile: (token: string, file: File) => api.stageRunFile(token, file),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** The shape lib/api's ApiError carries — the hook reads it structurally. */
const apiError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { name: "ApiError", status });

function pdf(name: string, size = 1): File {
  const file = new File(["%PDF"], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

beforeEach(() => {
  api.stageRunFile.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useStagedDocuments", () => {
  it("moves a document from staging to staged and exposes its stage id", async () => {
    const stage = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValue(stage.promise);
    const { result } = renderHook(() => useStagedDocuments());

    let key = -1;
    act(() => {
      key = result.current.stage(pdf("a.pdf"), "jwt");
    });
    expect(result.current.documents).toEqual([{ key, name: "a.pdf", status: "staging" }]);
    expect(result.current.gate).toEqual({ kind: "staging", count: 1 });

    await act(async () => stage.resolve({ stage_id: "stage-a" }));

    expect(result.current.documents).toEqual([{ key, name: "a.pdf", status: "staged", stageId: "stage-a" }]);
    expect(result.current.stagedUploads).toEqual([{ name: "a.pdf", stageId: "stage-a", attachIndex: key }]);
    expect(result.current.gate).toEqual({ kind: "ready" });
  });

  it("records a 413 as failed with the too-large reason and blocks the gate", async () => {
    api.stageRunFile.mockRejectedValue(apiError(413));
    const { result } = renderHook(() => useStagedDocuments());

    await act(async () => {
      result.current.stage(pdf("big.pdf"), "jwt");
    });

    expect(result.current.documents[0]).toMatchObject({ status: "failed", reason: UPLOAD_TOO_LARGE_MESSAGE });
    expect(result.current.stagedUploads).toEqual([]);
    expect(result.current.gate).toEqual({ kind: "failed", names: ["big.pdf"] });
  });

  it("fails an over-limit file without calling the server", () => {
    const { result } = renderHook(() => useStagedDocuments());

    act(() => {
      result.current.stage(pdf("huge.pdf", 10 * 1024 * 1024 + 1), "jwt");
    });

    expect(api.stageRunFile).not.toHaveBeenCalled();
    expect(result.current.documents[0]).toMatchObject({ status: "failed", reason: UPLOAD_TOO_LARGE_MESSAGE });
  });

  it("settle() resolves only after a pending stage has settled", async () => {
    const stage = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValue(stage.promise);
    const { result } = renderHook(() => useStagedDocuments());
    act(() => {
      result.current.stage(pdf("a.pdf"), "jwt");
    });
    expect(result.current.hasPending()).toBe(true);

    let settled: unknown = null;
    const waiting = result.current.settle().then((docs) => {
      settled = docs;
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(settled).toBeNull();

    await act(async () => {
      stage.resolve({ stage_id: "stage-a" });
      await waiting;
    });
    expect(settled).toEqual([expect.objectContaining({ status: "staged", stageId: "stage-a" })]);
    expect(result.current.hasPending()).toBe(false);
  });

  it("retry turns a failed document into a staged one under the same key", async () => {
    api.stageRunFile
      .mockRejectedValueOnce(apiError(502))
      .mockResolvedValueOnce({ stage_id: "stage-retried" });
    const { result } = renderHook(() => useStagedDocuments());
    let key = -1;
    await act(async () => {
      key = result.current.stage(pdf("a.pdf"), "jwt");
    });
    expect(result.current.documents[0]).toMatchObject({ status: "failed", reason: UPLOAD_FAILED_MESSAGE });

    let ok = false;
    await act(async () => {
      ok = await result.current.retry(key, "jwt");
    });

    expect(ok).toBe(true);
    expect(result.current.stagedUploads).toEqual([{ name: "a.pdf", stageId: "stage-retried", attachIndex: key }]);
    expect(result.current.gate).toEqual({ kind: "ready" });
  });

  it("remove drops the document and ignores its late response", async () => {
    const stage = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValue(stage.promise);
    const { result } = renderHook(() => useStagedDocuments());
    let key = -1;
    act(() => {
      key = result.current.stage(pdf("a.pdf"), "jwt");
    });

    act(() => result.current.remove(key));
    await act(async () => stage.resolve({ stage_id: "stage-late" }));

    expect(result.current.documents).toEqual([]);
    expect(result.current.stagedUploads).toEqual([]);
    expect(result.current.gate).toEqual({ kind: "ready" });
  });

  it("keeps attach order in attachIndex while stagedUploads follows arrival order", async () => {
    const first = deferred<{ stage_id: string }>();
    const second = deferred<{ stage_id: string }>();
    api.stageRunFile.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useStagedDocuments());
    act(() => {
      result.current.stage(pdf("a.pdf"), "jwt");
      result.current.stage(pdf("b.pdf"), "jwt");
    });

    await act(async () => second.resolve({ stage_id: "stage-b" }));
    await act(async () => first.resolve({ stage_id: "stage-a" }));

    expect(result.current.stagedUploads.map((s) => s.stageId)).toEqual(["stage-b", "stage-a"]);
    const byAttach = [...result.current.stagedUploads].sort((x, y) => x.attachIndex - y.attachIndex);
    expect(byAttach.map((s) => s.stageId)).toEqual(["stage-a", "stage-b"]);
  });
});

describe("uploadGateFor / uploadGateMessage", () => {
  it("is ready with no documents and says nothing", () => {
    expect(uploadGateFor([])).toEqual({ kind: "ready" });
    expect(uploadGateMessage({ kind: "ready" })).toBeNull();
  });

  it("prefers a failure over in-flight stages and names the failed files", () => {
    const gate = uploadGateFor([
      { key: 0, name: "a.pdf", status: "staging" },
      { key: 1, name: "b.pdf", status: "failed", reason: "x" },
    ]);
    expect(gate).toEqual({ kind: "failed", names: ["b.pdf"] });
    expect(uploadGateMessage(gate)).toBe("Upload failed for b.pdf. Remove or retry it to continue.");
  });

  it("counts in-flight stages", () => {
    expect(uploadGateMessage({ kind: "staging", count: 1 })).toBe("Uploading 1 document…");
    expect(uploadGateMessage({ kind: "staging", count: 2 })).toBe("Uploading 2 documents…");
  });
});
