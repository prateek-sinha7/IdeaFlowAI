import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";

// ─────────────────────────────────────────────────────────────────
// ISS-557 — CodeViewer.handleCopy (AppBuilderPreview.tsx:240-246) fires
// navigator.clipboard.writeText unawaited and calls setCopied(true)
// unconditionally right after, regardless of whether the write promise
// ever resolves. A rejected write must not claim "Copied".
// ─────────────────────────────────────────────────────────────────

const FILE: ParsedFile = {
  path: "src/index.tsx",
  name: "index.tsx",
  ext: "tsx",
  content: "export default function App() { return null; }",
  language: "tsx",
};

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

describe("AppBuilderPreview CodeViewer Copy button — ISS-557", () => {
  it("does not claim 'Copied' when the clipboard write silently rejects", async () => {
    render(<AppBuilderPreview files={[FILE]} projectName="Demo" />);

    fireEvent.click(await screen.findByRole("button", { name: /^Copy$/ }));

    // Let the fire-and-forget rejected microtask settle.
    await new Promise((r) => setTimeout(r, 0));

    // ISS-557: today this claims "Copied" unconditionally, even though the
    // write above rejected. The fixed behaviour must not show "Copied" here.
    expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  });
});
