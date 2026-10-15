import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SandboxPdfPreview } from "./SandboxPdfPreview";

const getRunSandboxFileBlob = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "tok",
  // ISS-1073 — the preview resolves the declared name at the ref first; here the tree holds it at the root.
  resolveRunDeliverable: async (_t: string, _r: string, path: string, ref?: string) => ({ path, ref }),
  getRunSandboxFileBlob: (...args: unknown[]) => getRunSandboxFileBlob(...args),
}));

describe("SandboxPdfPreview", () => {
  it("fetches the file with the token and frames it as a PDF", async () => {
    getRunSandboxFileBlob.mockResolvedValueOnce(new Blob(["%PDF-1.7"], { type: "application/octet-stream" }));
    const created: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((b) => { created.push(b as Blob); return "blob:pdf"; });
    render(<SandboxPdfPreview runId="run-1" path="Backlog.pdf" fallback={<p>md</p>} />);
    const frame = await screen.findByTestId("sandbox-pdf-preview");
    expect(frame.getAttribute("src")).toBe("blob:pdf");
    // ISS-973: the read now carries the member's ref slot; none given = the live tree.
    expect(getRunSandboxFileBlob).toHaveBeenCalledWith("tok", "run-1", "Backlog.pdf", undefined);
    expect(created[0].type).toBe("application/pdf");
  });

  it("renders the fallback when the PDF cannot be read", async () => {
    getRunSandboxFileBlob.mockRejectedValueOnce(new Error("404: could not download Backlog.pdf"));
    render(<SandboxPdfPreview runId="run-1" path="Backlog.pdf" fallback={<p>md fallback</p>} />);
    expect(await screen.findByText("md fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("sandbox-pdf-preview")).not.toBeInTheDocument();
  });
});
