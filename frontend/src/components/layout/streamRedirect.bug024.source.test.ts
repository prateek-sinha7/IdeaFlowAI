/**
 * BUG-024 / QA-KB-049 — the isRunning effect in DashboardLayout.tsx pushes
 * routes.runStream(incomingRunId) unconditionally, so cold-loading
 * /runs/{id}/audit|files|steps of a generating run is rewritten to /stream.
 * Correct behaviour: the push is skipped when the URL already addresses that
 * run (pathname or parseViewPath). Fails today (the push is bare).
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("DashboardLayout isRunning effect — BUG-024 keep requested run tab", () => {
  it("does not push /stream unconditionally when the URL already addresses the run", () => {
    const src = readFileSync(path.join(__dirname, "DashboardLayout.tsx"), "utf8");
    const at = src.indexOf("router.push(routes.runStream(incomingRunId))");
    expect(at).toBeGreaterThan(-1);
    const before = src.slice(Math.max(0, at - 600), at);
    expect(before).toMatch(/pathname|parseViewPath|location\.pathname/);
  });
});
