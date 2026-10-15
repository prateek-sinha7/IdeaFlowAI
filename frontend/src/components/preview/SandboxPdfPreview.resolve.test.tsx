import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";

// ISS-1073 / QA-KB-096 — the PDF preview asks a version tag for the run's DECLARED
// root path, but the root Backlog.pdf is gitignored: a tag holds .chain/Backlog.pdf
// (v2+) or no PDF at all (v1). It must resolve against the listing AT the ref first
// (resolveRunDeliverable) and read the resolved path; a null resolve sends no file read.

const mockBlob = vi.fn();
const mockResolve = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  resolveRunDeliverable: (...args: unknown[]) => mockResolve(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => mockBlob(...args),
}));

import { SandboxPdfPreview } from "./SandboxPdfPreview";

describe("SandboxPdfPreview — resolves the deliverable at the member's ref (ISS-1073)", () => {
  beforeEach(() => {
    mockBlob.mockReset();
    mockResolve.mockReset();
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
  });

  it("ISS-1073: reads the resolved .chain/ path at v2, not the declared root path", async () => {
    mockResolve.mockResolvedValue({ path: ".chain/Backlog.pdf", ref: "v2" });
    mockBlob.mockResolvedValue(new Blob(["%PDF"]));

    render(<SandboxPdfPreview runId="run-1" path="Backlog.pdf" selectedRef="v2" fallback={null} />);

    await waitFor(() => expect(mockBlob).toHaveBeenCalled());
    expect(mockBlob.mock.calls[0][2]).toBe(".chain/Backlog.pdf");
    expect(mockBlob.mock.calls[0][3]).toBe("v2");
    // Resolved WITHOUT the ref, the listing is the live tree: it finds the root copy and the read at v2 404s again.
    expect(mockResolve).toHaveBeenCalledWith("test-token", "run-1", "Backlog.pdf", "v2");
  });

  it("ISS-1073: sends no file request and shows the fallback when v1 holds no PDF", async () => {
    mockResolve.mockResolvedValue(null);
    mockBlob.mockRejectedValue(new Error("404"));

    const { findByText } = render(
      <SandboxPdfPreview runId="run-1" path="Backlog.pdf" selectedRef="v1" fallback={<p>fallback shown</p>} />,
    );

    await findByText("fallback shown");
    expect(mockResolve).toHaveBeenCalled();
    expect(mockBlob).not.toHaveBeenCalled();
  });
});
