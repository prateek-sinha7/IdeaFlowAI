import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InputPromptSection } from "./AgentDetailPanel";

// ─────────────────────────────────────────────────────────────────
// ISS-556 — InputPromptSection.handleCopy (AgentDetailPanel.tsx:446-450)
// fires navigator.clipboard.writeText unawaited and calls setCopied(true)
// unconditionally on the very next line, regardless of whether the write
// promise ever resolves. A rejected write must still report "Copied".
// ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

describe("InputPromptSection Copy button — ISS-556", () => {
  it("does not claim 'Copied' when the clipboard write silently rejects", async () => {
    render(<InputPromptSection prompt="the full prompt text" />);
    fireEvent.click(screen.getByRole("button", { name: /Full input prompt/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Copy$/ }));

    // Let the rejected microtask settle.
    await new Promise((r) => setTimeout(r, 0));

    // ISS-556: today this claims "Copied" unconditionally, even though the
    // write above rejected. The fixed behaviour must not show "Copied" here.
    expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  });
});
