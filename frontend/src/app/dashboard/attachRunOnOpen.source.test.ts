import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// BUG-013 (260716-r7d) — page-wiring source-lock. On reopen,
// `handleSelectWorkflowRun` must attach the VIEWED run as the single sticky
// SSE focus so a parked/building run streams live (multi-round clarify +
// resume→build) without waiting on the next refreshLiveRuns poll. The huge
// page.tsx is impractical to render, so this uses the sanctioned grep-style
// source assertion (mirrors contentSourceRunType.source.test.ts).
//
// PLAN-CHECKER GATE: the attach fires ONLY for a NON-TERMINAL run. A terminal
// run (completed/failed/cancelled/degraded) emits nothing, so focusing it would
// pin a dead-stream reconnect loop for the session — the gate excludes it.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const collapsed = pageSource.replace(/\s+/g, " ");

function collapse(s: string): string {
  return s.replace(/\s+/g, " ");
}

describe("BUG-013 reopen attaches the viewed run as focus (source-lock)", () => {
  it("declares the reopen-terminal status set covering all four terminal statuses", () => {
    // FAIL-BEFORE: no such set exists — RED.
    expect(collapsed).toContain(
      collapse(
        'const REOPEN_TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "degraded"]);',
      ),
    );
  });

  it("reopen calls runConnection.attachRun(fullRun.id), GATED on non-terminal", () => {
    // FAIL-BEFORE: handleSelectWorkflowRun never attaches the viewed run — RED.
    expect(collapsed).toContain(
      collapse(
        "if (!REOPEN_TERMINAL_STATUSES.has(fullRun.status)) { runConnection.attachRun(fullRun.id); }",
      ),
    );
  });

  it("the attach is adjacent to the durable content-source binding", () => {
    // Anchors the attach inside the reopen handler next to setContentSourceRunId.
    expect(pageSource).toContain("setContentSourceRunId(fullRun.id);");
  });
});
