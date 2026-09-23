import { describe, expect, it } from "vitest";
import { orderedStagedUploadIds } from "./IdeaInputPage";

// Reproduces the reported bug: 5 files attached 1..5 (crimson.pdf, amber.docx,
// verdant.pptx, azure.xlsx, violet.pdf) whose stage POST responses resolve
// out of attach order (3, 2, 1, 5, 4 — arrival order). `attachIndex` (stamped
// synchronously in handleFiles, before the async stage call) is the only
// signal that survives — `orderedStagedUploadIds` sorts on it to recover
// true attach order regardless of the array's append order.
describe("orderedStagedUploadIds", () => {
  it("recovers attach order from out-of-arrival-order stage responses", () => {
    const stagedUploads = [
      { name: "3-verdant.pptx", stageId: "stage-3", attachIndex: 2 },
      { name: "2-amber.docx", stageId: "stage-2", attachIndex: 1 },
      { name: "1-crimson.pdf", stageId: "stage-1", attachIndex: 0 },
      { name: "5-violet.pdf", stageId: "stage-5", attachIndex: 4 },
      { name: "4-azure.xlsx", stageId: "stage-4", attachIndex: 3 },
    ];

    expect(orderedStagedUploadIds(stagedUploads)).toEqual([
      "stage-1", "stage-2", "stage-3", "stage-4", "stage-5",
    ]);
  });

  it("keeps separate attach actions in order (indices need not be contiguous within one batch)", () => {
    // First drop: 2 files (indices 0, 1). Second drop: 1 more file (index 2).
    // Responses can still resolve in any order.
    const stagedUploads = [
      { name: "c.pdf", stageId: "c", attachIndex: 2 },
      { name: "a.pdf", stageId: "a", attachIndex: 0 },
      { name: "b.pdf", stageId: "b", attachIndex: 1 },
    ];

    expect(orderedStagedUploadIds(stagedUploads)).toEqual(["a", "b", "c"]);
  });

  it("does not mutate the input array", () => {
    const stagedUploads = [
      { name: "b.pdf", stageId: "b", attachIndex: 1 },
      { name: "a.pdf", stageId: "a", attachIndex: 0 },
    ];
    const copy = [...stagedUploads];

    orderedStagedUploadIds(stagedUploads);

    expect(stagedUploads).toEqual(copy);
  });

  it("returns an empty array for no staged uploads", () => {
    expect(orderedStagedUploadIds([])).toEqual([]);
  });
});
