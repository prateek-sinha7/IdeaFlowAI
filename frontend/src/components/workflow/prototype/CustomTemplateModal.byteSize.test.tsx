import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomTemplateModal } from "./CustomTemplateModal";

// ─────────────────────────────────────────────────────────────────
// ISS-589 — CustomTemplateModal.tsx uses htmlBody.length (UTF-16 code
// units) for two distinct purposes, both wrong vs the true UTF-8 byte
// size: the "Loaded X KB" display label (line 232) and the "max 2 MB"
// upload gate (line 80). Two tests, one per named condition.
// ─────────────────────────────────────────────────────────────────

describe("CustomTemplateModal size handling — ISS-589", () => {
  it("'Loaded X KB' reflects the true UTF-8 byte size, not the UTF-16 char count", async () => {
    const user = userEvent.setup();
    render(<CustomTemplateModal onConfirm={vi.fn()} onClose={vi.fn()} />);

    // "é—" repeated: each repeat is 2 UTF-16 units but 5 UTF-8 bytes, so char
    // KB and byte KB land in different "X.X KB" buckets.
    const content = "é—".repeat(200);
    const trueKb = (new TextEncoder().encode(content).length / 1024).toFixed(1);
    const charKb = (content.length / 1024).toFixed(1);
    expect(trueKb).not.toBe(charKb); // sanity: the content actually exercises the bug

    const file = new File([content], "template.html", { type: "text/html" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    // "Loaded X KB" is split across sibling text nodes (literal + JSX
    // expression); match on the paragraph's combined textContent.
    await waitFor(() => {
      const p = screen.getByText(/^Loaded/).closest("p") as HTMLElement;
      // Today this shows `Loaded ${charKb} KB` instead of the true byte-derived value.
      expect(p.textContent).toContain(`Loaded ${trueKb} KB`);
    });
  });

  it("rejects an upload whose true byte size exceeds the 2 MB cap even when its char count does not", async () => {
    const user = userEvent.setup();
    render(<CustomTemplateModal onConfirm={vi.fn()} onClose={vi.fn()} />);

    // Every char is 2 UTF-8 bytes ("é"), so a string whose char length sits
    // AT the 2 MB threshold (not > it, so the buggy char-length check lets it
    // through) has a true byte size of double that — well over the cap.
    const CAP = 2 * 1024 * 1024;
    const content = "é".repeat(CAP);
    expect(content.length).toBe(CAP);
    expect(new TextEncoder().encode(content).length).toBeGreaterThan(CAP);

    const file = new File([content], "huge.html", { type: "text/html" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    // Today the char-length gate lets this through silently (no error, no
    // rejection) even though the true byte size is over the 2 MB cap.
    await waitFor(() => expect(screen.getByText(/too large/i)).toBeInTheDocument());
  });
});
