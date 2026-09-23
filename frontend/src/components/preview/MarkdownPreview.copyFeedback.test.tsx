import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MarkdownPreview } from "./MarkdownPreview";

// ─────────────────────────────────────────────────────────────────
// ISS-558 — both MarkdownPreview.handleCopyAll (L49-53, the header
// "Copy All" button) and CodeBlock.handleCopy (L174-178, the per-fenced-
// code-block Copy button) fire navigator.clipboard.writeText unawaited and
// call setCopied(true) unconditionally right after. Neither must claim
// success when the write silently rejects. Two distinct call sites named
// by the card -> two tests.
// ─────────────────────────────────────────────────────────────────

const CONTENT = "# Heading\n\nSome body text.\n\n```ts\nconst x = 1;\n```\n";

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

describe("MarkdownPreview 'Copy All' button — ISS-558", () => {
  it("does not claim 'Copied!' when the clipboard write silently rejects", async () => {
    render(<MarkdownPreview content={CONTENT} />);
    fireEvent.click(screen.getByRole("button", { name: /Copy All/i }));

    await new Promise((r) => setTimeout(r, 0));

    // ISS-558: today this claims "Copied!" unconditionally.
    expect(screen.queryByText("Copied!")).not.toBeInTheDocument();
  });
});

describe("MarkdownPreview code-block Copy button — ISS-558", () => {
  it("does not claim 'Copied' when the clipboard write silently rejects", async () => {
    render(<MarkdownPreview content={CONTENT} />);
    fireEvent.click(screen.getByRole("button", { name: /^Copy$/ }));

    await new Promise((r) => setTimeout(r, 0));

    // ISS-558: today this claims "Copied" unconditionally.
    expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  });
});
