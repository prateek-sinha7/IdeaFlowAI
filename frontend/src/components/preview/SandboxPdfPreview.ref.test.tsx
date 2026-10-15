import { describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

// ISS-973 (sibling of ISS-665 / QA-KB-053) — SandboxPdfPreview has no ref
// parameter, so an older family member's PDF preview reads the live (newest)
// tree. Fixed: it accepts a ref and forwards it to getRunSandboxFileBlob.

const mockBlob = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  // ISS-1073 — the preview resolves the declared name at the ref first; here the tree holds it at the root.
  resolveRunDeliverable: async (_t: string, _r: string, path: string, ref?: string) => ({ path, ref }),
  getRunSandboxFileBlob: (...args: unknown[]) => mockBlob(...args),
}));

import { SandboxPdfPreview } from "./SandboxPdfPreview";

describe("SandboxPdfPreview — ref threading (ISS-973)", () => {
  it("ISS-973: forwards a supplied ref to getRunSandboxFileBlob", async () => {
    mockBlob.mockResolvedValue(new Blob(["%PDF"]));
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();

    render(<SandboxPdfPreview runId="run-1" path="Backlog.pdf" selectedRef="v2" fallback={null} />);

    await waitFor(() => expect(mockBlob).toHaveBeenCalled());
    expect(mockBlob.mock.calls[0][3]).toBe("v2");
  });
});
