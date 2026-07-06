import { describe, expect, it } from "vitest";
import { parseRunInput } from "./runInput";

// ─────────────────────────────────────────────────────────────────
// Workstream C1 (POR §6.1 / §7) — parseRunInput is the SINGLE FE-owned
// marker parser. Pure-lib unit tests (no DOM), cloning the workflowChaining
// vitest idiom. Every marker format here is FE-composed elsewhere (exact,
// non-heuristic) — the anchors are cited beside each case.
// ─────────────────────────────────────────────────────────────────

describe("parseRunInput — plain / instruction-only pass-through", () => {
  it("returns a plain brief unchanged with no attachments", () => {
    const input = "Build me a todo app with dark mode.";
    const r = parseRunInput(input);
    expect(r.brief).toBe(input);
    expect(r.attachments).toEqual([]);
    expect(r.revisionInstruction).toBeUndefined();
    expect(r.existingArtifactBlock).toBeUndefined();
    expect(r.chainContext).toBeUndefined();
    expect(r.preferences).toBeUndefined();
  });

  it("passes a clean instruction-only string (post-Phase-D shape) through as brief", () => {
    const input = "Make the header sticky and add a footer.";
    const r = parseRunInput(input);
    expect(r.brief).toBe(input);
    expect(r.revisionInstruction).toBeUndefined();
  });
});

describe("parseRunInput — attachments (=== Attached: {name} === … === End: {name} ===)", () => {
  it("strips two attachment blocks from the brief and collects name+content", () => {
    // Mirrors IdeaInputPage.tsx:542 — the FE composes `\n\n=== Attached: … ===`.
    const input =
      "Design a landing page." +
      "\n\n=== Attached: brand.md ===\n# Brand colors\nblue\n=== End: brand.md ===" +
      "\n\n=== Attached: copy.txt ===\nHero: Welcome\n=== End: copy.txt ===";
    const r = parseRunInput(input);
    expect(r.brief).toBe("Design a landing page.");
    expect(r.attachments.length).toBe(2);
    expect(r.attachments[0]).toEqual({ name: "brand.md", content: "# Brand colors\nblue" });
    expect(r.attachments[1]).toEqual({ name: "copy.txt", content: "Hero: Welcome" });
  });
});

describe("parseRunInput — inline revision blob (asymmetric EXISTING + REVISION REQUEST)", () => {
  it("decomposes existingArtifactBlock + revisionInstruction, brief empty", () => {
    // Mirrors DashboardLayout.tsx:534 — open `=== EXISTING PROTOTYPE HTML ===`,
    // close `=== END EXISTING HTML ===` (asymmetric labels).
    const input =
      "=== EXISTING PROTOTYPE HTML ===\n<html><body>hi</body></html>\n=== END EXISTING HTML ===" +
      "\n\n=== REVISION REQUEST ===\nmake the header blue\n=== END REQUEST ===";
    const r = parseRunInput(input);
    expect(r.revisionInstruction).toBe("make the header blue");
    expect(r.existingArtifactBlock).toContain("<html><body>hi</body></html>");
    expect(r.brief).toBe("");
  });

  it("is format-tolerant: an UNCLOSED revision request still yields the instruction (B2 shim shape)", () => {
    // The B2 timeline test feeds exactly this unclosed form.
    const input = "=== REVISION REQUEST ===\nmake the header blue";
    const r = parseRunInput(input);
    expect(r.revisionInstruction).toBe("make the header blue");
    expect(r.brief).toBe("");
  });
});

describe("parseRunInput — chain context + preferences", () => {
  it("captures chainContext and keeps the leading brief", () => {
    // Mirrors DashboardLayout.tsx:926 chain composition.
    const input =
      "Turn this into slides." +
      "\n\n=== CONTEXT FROM PREVIOUS PIPELINE (prototype) ===\nprior output here\n=== END PREVIOUS CONTEXT ===";
    const r = parseRunInput(input);
    expect(r.brief).toBe("Turn this into slides.");
    expect(r.chainContext).toContain("prior output here");
  });

  it("captures user preferences", () => {
    const input =
      "Ship it." +
      "\n\n=== USER PREFERENCES ===\ntone: formal\nlength: short\n=== END PREFERENCES ===";
    const r = parseRunInput(input);
    expect(r.brief).toBe("Ship it.");
    expect(r.preferences).toContain("tone: formal");
  });
});
