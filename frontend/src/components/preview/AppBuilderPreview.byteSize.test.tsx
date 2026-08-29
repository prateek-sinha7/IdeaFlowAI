import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";

// ─────────────────────────────────────────────────────────────────
// ISS-588 — AppBuilderPreview.tsx:556 sums f.content.length across every
// listed file for the footer's "X KB total". String.prototype.length
// counts UTF-16 code units, not UTF-8 bytes, so files with multi-byte
// UTF-8 content (comments, string literals, i18n text) understate the
// total — same mechanism as ISS-351, compounding across files.
// ─────────────────────────────────────────────────────────────────

// "é—" repeated 200x per file: each repeat is 2 UTF-16 units but 5 UTF-8
// bytes, so the summed char count and summed byte count land in different
// "X.X KB" buckets.
const CONTENT = "é—".repeat(200);
const FILES: ParsedFile[] = [
  { path: "src/a.ts", name: "a.ts", ext: "ts", content: CONTENT, language: "ts" },
  { path: "src/b.ts", name: "b.ts", ext: "ts", content: CONTENT, language: "ts" },
];

describe("AppBuilderPreview footer 'KB total' — ISS-588", () => {
  it("sums the true UTF-8 byte size across files, not the UTF-16 char count", () => {
    const trueKb = (
      FILES.reduce((s, f) => s + new TextEncoder().encode(f.content).length, 0) / 1024
    ).toFixed(1);
    const charKb = (FILES.reduce((s, f) => s + f.content.length, 0) / 1024).toFixed(1);
    expect(trueKb).not.toBe(charKb); // sanity: the content actually exercises the bug

    render(<AppBuilderPreview files={FILES} projectName="Demo" />);

    // The footer line is one <p> built from multiple JSX expressions/text
    // nodes; match on its combined textContent rather than a single node.
    const footer = screen.getByText(/files total|KB total/).closest("p") as HTMLElement;
    // Today the footer shows `${charKb} KB total` (summed chars) instead of
    // the true byte-derived total.
    expect(footer.textContent).toContain(`${trueKb} KB total`);
  });
});
