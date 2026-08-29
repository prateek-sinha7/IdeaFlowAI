import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { UserStoryPreview } from "./UserStoryPreview";

// ─────────────────────────────────────────────────────────────────
// ISS-559 — UserStoryPreview.handleCopy (UserStoryPreview.tsx:47-51) fires
// navigator.clipboard.writeText unawaited and calls setCopied(true)
// unconditionally right after, regardless of whether the write promise
// ever resolves. A rejected write must not claim "Copied".
// ─────────────────────────────────────────────────────────────────

// No "# " heading -> parseUserStoryMarkdown yields zero epics, which
// renders the simple raw-content view with a single "Copy MD" button.
const CONTENT = "plain text with no epic markers";

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

describe("UserStoryPreview Copy MD button — ISS-559", () => {
  it("does not claim 'Copied' when the clipboard write silently rejects", async () => {
    render(<UserStoryPreview content={CONTENT} />);
    fireEvent.click(screen.getByRole("button", { name: /Copy MD/i }));

    await new Promise((r) => setTimeout(r, 0));

    // ISS-559: today this claims "Copied" unconditionally.
    expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  });
});
