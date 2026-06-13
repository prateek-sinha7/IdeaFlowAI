import { describe, expect, it } from "vitest";

import { deriveDeliverableMimetype } from "./index";

// ─── ISS-021 (18-03 Task 1) — shared reopen mimetype-derivation heuristic ─────
// This is the SINGLE source of truth both reopen surfaces (page.tsx generic
// channel + WorkflowHistory.tsx detail view) import, so they cannot diverge.
describe("deriveDeliverableMimetype — shared reopen heuristic", () => {
  it("a <!doctype html> prefix → text/html", () => {
    expect(deriveDeliverableMimetype("<!doctype html>\n<html><body>hi</body></html>")).toBe("text/html");
  });

  it("a <html> prefix (no doctype) → text/html", () => {
    expect(deriveDeliverableMimetype("<html><head></head><body>x</body></html>")).toBe("text/html");
  });

  it("is case-insensitive and tolerates leading whitespace", () => {
    expect(deriveDeliverableMimetype("   \n  <!DOCTYPE HTML>")).toBe("text/html");
    expect(deriveDeliverableMimetype("\n\t<HTML>")).toBe("text/html");
  });

  it("markdown / plain text → text/markdown", () => {
    expect(deriveDeliverableMimetype("# A Heading\n\nbody text")).toBe("text/markdown");
    expect(deriveDeliverableMimetype("just some prose")).toBe("text/markdown");
  });

  it("an HTML fragment WITHOUT a doc/html prefix is treated as markdown (not framed)", () => {
    // A bare <div> is not a full document — the heuristic only frames declared
    // documents to avoid framing arbitrary inline HTML snippets.
    expect(deriveDeliverableMimetype("<div>hello</div>")).toBe("text/markdown");
  });

  // ─── WR-02 (18 review) — serialized-sandbox bundle detection ────────────────
  it("a ```filename: …``` bundle → application/zip (not mis-typed to markdown)", () => {
    const bundle = "Here is the app:\n\n```filename: app/main.py\nprint('hi')\n```\n";
    expect(deriveDeliverableMimetype(bundle)).toBe("application/zip");
  });

  it("bundle detection is case-insensitive on the filename: marker", () => {
    expect(deriveDeliverableMimetype("```FILENAME: a.ts\nx\n```")).toBe("application/zip");
  });

  it("markdown that merely mentions the word filename (no fenced block) stays text/markdown", () => {
    expect(deriveDeliverableMimetype("The filename is config.json — see below.")).toBe("text/markdown");
  });

  it("empty / null / whitespace output → text/markdown (nothing to frame)", () => {
    expect(deriveDeliverableMimetype("")).toBe("text/markdown");
    expect(deriveDeliverableMimetype(null)).toBe("text/markdown");
    expect(deriveDeliverableMimetype(undefined)).toBe("text/markdown");
    expect(deriveDeliverableMimetype("   \n  ")).toBe("text/markdown");
  });
});
