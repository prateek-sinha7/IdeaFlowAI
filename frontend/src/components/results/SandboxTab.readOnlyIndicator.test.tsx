import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SandboxTab } from "./SandboxTab";
import type { SandboxFile } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// BUG-20260828-013500-runs-id-workspace / ISS-383, ISS-597.
//
// CodeView's own doc comment (SandboxTab.tsx:479) claims "CodeMirror 6,
// read-only" but its EditorView extensions never set readOnly/editable, and
// nothing in the rendered pane signals it is a live, keystroke-accepting
// scratchpad — no lock icon, no "read-only"/"scratchpad" label, no
// Save/Discard affordance. These specs pin the two call sites CodeView has
// (SandboxTab.tsx:411 markdown-fence, :1331 explicit Code toggle) each
// showing SOME visible indication when the pane is editable. Scaffold
// mirrors SandboxTab.test.tsx.
// ─────────────────────────────────────────────────────────────────

const getRunSandbox = vi.fn();
const getRunSandboxFile = vi.fn();
const getRunSandboxFileBlob = vi.fn();
const getRunSandboxZip = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getRunSandbox: (...args: unknown[]) => getRunSandbox(...args),
  getRunSandboxFile: (...args: unknown[]) => getRunSandboxFile(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => getRunSandboxFileBlob(...args),
  getRunSandboxZip: (...args: unknown[]) => getRunSandboxZip(...args),
}));

vi.mock("./FilesTab", () => ({ downloadBlob: vi.fn() }));

const f = (
  path: string,
  size: number,
  extra: Partial<SandboxFile> = {},
): SandboxFile => ({ path, size, modified: 1, text: true, kind: "text", deliverable: true, ...extra });

const READ_ONLY_INDICATOR = /read.only|scratchpad|not saved|preview only|view.only/i;

beforeEach(() => {
  getRunSandbox.mockReset();
  getRunSandboxFile.mockReset();
  getRunSandboxFileBlob.mockReset();
  getRunSandboxZip.mockReset();
});

describe("CodeView read-only indication (ISS-383)", () => {
  it("ISS-383: shows a visible read-only/scratchpad indicator on the explicit Code-toggle surface", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("build.js", 40, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue("const a = 1;\nconst b = 2;");
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("build.js")).toBeInTheDocument());
    await userEvent.click(screen.getByText("build.js"));
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());

    // The pane is a live, typeable CodeMirror instance (its own contract, per
    // .cm-content's contenteditable). Nothing on screen says so.
    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("true");
    expect(document.body.textContent).toMatch(READ_ONLY_INDICATOR);
  });
});

describe("CodeView read-only indication on the markdown-fence surface (ISS-597)", () => {
  it("ISS-597: shows the SAME visible indicator for a fenced code block in a markdown file's default Preview — no Code toggle clicked", async () => {
    getRunSandbox.mockResolvedValue({
      run_id: "run-1",
      expired: false,
      truncated: false,
      files: [f("PLANNER.md", 40, { deliverable: false })],
    });
    getRunSandboxFile.mockResolvedValue(
      "# Plan\n\nSome notes.\n\n```json\n{\"a\": 1}\n```\n",
    );
    render(<SandboxTab runId="run-1" />);
    await waitFor(() => expect(screen.getByText("PLANNER.md")).toBeInTheDocument());
    await userEvent.click(screen.getByText("PLANNER.md"));

    // Default is markdown-rendered Preview — no "Code" toggle was clicked.
    expect(screen.queryByRole("button", { name: /^code$/i })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());

    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("true");
    expect(document.body.textContent).toMatch(READ_ONLY_INDICATOR);
  });
});
