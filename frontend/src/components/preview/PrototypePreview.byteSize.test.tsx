import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PrototypePreview } from "./PrototypePreview";

// ─────────────────────────────────────────────────────────────────
// ISS-587 — PrototypePreview.tsx:570 labels renderedHtml.length/1024 as
// "KB" in the source view. String.prototype.length counts UTF-16 code
// units, not UTF-8 bytes, so content with multi-byte UTF-8 characters
// (em dashes, arrows, accented letters) is understated — same mechanism
// as ISS-351.
// ─────────────────────────────────────────────────────────────────

// "é—" repeated: each repeat is 2 UTF-16 units but 5 UTF-8 bytes, so char
// count and byte count diverge enough to land in different "X.X KB" buckets.
const CONTENT = "<!DOCTYPE html><html><body>" + "é—".repeat(400) + "</body></html>";

describe("PrototypePreview source-view size label — ISS-587", () => {
  it("shows the true UTF-8 byte size of renderedHtml, not its UTF-16 char count", async () => {
    render(<PrototypePreview content={CONTENT} />);

    fireEvent.click(await screen.findByTitle("View source"));
    await screen.findByText("index.html");

    const trueKb = (new TextEncoder().encode(CONTENT).length / 1024).toFixed(1);
    const charKb = (CONTENT.length / 1024).toFixed(1);
    expect(trueKb).not.toBe(charKb); // sanity: the content actually exercises the bug

    // The "X.X KB" label sits next to "index.html" as sibling text nodes
    // (JSX expression + literal), so match on the header's combined
    // textContent rather than a single text node.
    const header = screen.getByText("index.html").parentElement as HTMLElement;
    // Today this shows `${charKb} KB` (computed from chars) instead of the
    // true byte-derived value.
    expect(header.textContent).toContain(`${trueKb} KB`);
  });
});
