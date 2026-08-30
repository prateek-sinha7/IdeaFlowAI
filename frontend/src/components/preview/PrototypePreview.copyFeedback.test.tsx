import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PrototypePreview } from "./PrototypePreview";

// ─────────────────────────────────────────────────────────────────
// ISS-560 — PrototypePreview.handleCopySource (PrototypePreview.tsx:391-398)
// chains navigator.clipboard.writeText(...).then(...) with no .catch(). A
// rejected write leaves the "Copy all" button stuck reading its default
// state forever, with nothing shown to the user.
// ─────────────────────────────────────────────────────────────────

const CONTENT = "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>";

beforeEach(() => {
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockRejectedValue(new DOMException("denied")) },
  });
});

// The defect this card asserts IS an unhandled promise rejection
// (handleCopySource's `.then()` has no `.catch()`) — that is exactly what
// makes the button silent. Swallow the process-level event so the real
// assertion below decides pass/fail instead of the test runner.
let restoreUnhandledRejection: (() => void) | undefined;
beforeEach(() => {
  const noop = () => {};
  process.on("unhandledRejection", noop);
  restoreUnhandledRejection = () => process.off("unhandledRejection", noop);
});
afterEach(() => {
  restoreUnhandledRejection?.();
});

describe("PrototypePreview 'Copy all' source button — ISS-560", () => {
  it("shows a failure state when the clipboard write rejects, instead of staying silent", async () => {
    render(<PrototypePreview content={CONTENT} />);

    // Reveal the source view, where "Copy all" lives.
    fireEvent.click(await screen.findByTitle("View source"));
    fireEvent.click(await screen.findByRole("button", { name: /Copy all/i }));

    // Let the rejected .then() chain settle (it never resolves — this just
    // gives any competing state update a tick to land).
    await new Promise((r) => setTimeout(r, 0));

    // ISS-560: today nothing changes on rejection — no failure text, button
    // stays "Copy all". The fixed behaviour must surface SOMETHING.
    expect(screen.queryByText(/fail|error|couldn.?t/i)).toBeInTheDocument();
  });
});
