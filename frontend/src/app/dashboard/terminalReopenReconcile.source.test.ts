import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// ISS-126 — page-wiring source-lock for the terminal-reopen reconciliation.
//
// A terminal run NEVER opens an SSE stream (`page.tsx:2171` gates attachRun on
// non-terminal), so the screen is rebuilt entirely from
// `GET /api/runs/{id}/events` replayed at :2234-2247. When that durable log has
// no terminal event — a run cancelled through an ISS-124 driver terminal, or one
// corrupted by the pre-FIX-240 seq collision — nothing resolves `isRunning` and
// the run renders as live ("Awaiting approval" + Stop). This pins the fix.
//
// ORDERING IS THE WHOLE POINT. Placed BEFORE the replay loop, the reconciliation
// is immediately overwritten by the replayed `review_gate_ready`/`pipeline_start`
// and the bug persists — while a naive "does it call it?" assertion still passes.
// So this test asserts POSITION, not just presence.
//
// The huge page.tsx is impractical to render, so this uses the sanctioned
// grep-style source assertion (mirrors attachRunOnOpen.source.test.ts).
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");

describe("ISS-126 reopen reconciles a terminal run (source-lock)", () => {
  it("imports the shared terminal reducer rather than re-deriving markers inline", () => {
    // FAIL-BEFORE: no such import — RED. INV-12: one vocabulary, imported.
    expect(pageSource).toMatch(/import\s*\{[^}]*applyTerminalStatus[^}]*\}\s*from\s*"@\/hooks\/useWorkflow"/);
  });

  it("gates the reconciliation on the EXISTING REOPEN_TERMINAL_STATUSES set", () => {
    // Reuses page.tsx:64 — the set that already matches the backend's
    // TERMINAL_STATUSES and already gates attachRun and the transcript seed.
    // A NEW list here would be the INV-12 violation the fix exists to avoid.
    expect(pageSource).toContain("REOPEN_TERMINAL_STATUSES.has(fullRun.status)");
    expect(pageSource).toContain("runStore.updatePipelineState(");
    expect(pageSource).toContain("applyTerminalStatus(prev, fullRun.status)");
  });

  it("reconciles BOTH containers — the store AND the legacy reducer state", () => {
    // PROVEN IN A BROWSER, not reasoned about: patching only the store is
    // TRANSIENT. The FIX-201 bridge (page.tsx:1663-1672) copies the legacy
    // useWorkflow.pipelineState into the store WHOLESALE once the viewport
    // switches to the reopened run, and that legacy state accumulated the same
    // terminal-less replay — so it clobbered the store patch a few hundred ms
    // later and the screen kept showing a live Stop.
    expect(pageSource).toContain("reconcileTerminalStatus(fullRun.status);");
    expect(pageSource).toMatch(/reconcileTerminalStatus\s*\}\s*=\s*useWorkflow\(\)|reconcileTerminalStatus\s*\}\s*=/);
  });

  it("clears the lingering clarify panel — the one branch not gated on isRunning", () => {
    // laneClarifyOpen (DashboardLayout:1862) is deliberately NOT AND-ed with
    // isRunning, because clarify precedes pipeline_start. So resolving isRunning
    // alone leaves the header reading "Clarifying" with Stop still armed.
    expect(pageSource).toContain("runStore.update(fullRun.id, { questionnaireData: null });");
  });

  it("does NOT clear reviewGateData — that would erase the historical gate card", () => {
    const call = pageSource.indexOf("applyTerminalStatus(prev, fullRun.status)");
    const windowAfter = pageSource.slice(call, call + 1600);
    expect(windowAfter).not.toContain("reviewGateData: null");
  });

  it("writes to the run STORE — the state the UI actually reads", () => {
    // page.tsx:2494 `displayedPipelineState = runStore.viewed.pipelineState` is
    // what DashboardLayout receives. The legacy React setters at :1197-1201 are
    // NOT read by the lane, so writing there would be invisible.
    expect(pageSource).toContain("const displayedPipelineState = runStore.viewed.pipelineState;");
    const call = pageSource.indexOf("applyTerminalStatus(prev, fullRun.status)");
    const storeWrite = pageSource.lastIndexOf("runStore.updatePipelineState(", call);
    expect(storeWrite).toBeGreaterThan(-1);
  });

  it("runs AFTER the durable replay loop, never before it", () => {
    const loopStart = pageSource.indexOf("for (const frame of durableFrames)");
    const call = pageSource.indexOf("applyTerminalStatus(prev, fullRun.status)");
    expect(loopStart).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(loopStart);
  });

  it("stays inside the reopen handler, after the durable fetch", () => {
    const fetchAt = pageSource.indexOf("const durableFrames = await getRunEvents(currentToken, fullRun.id);");
    const call = pageSource.indexOf("applyTerminalStatus(prev, fullRun.status)");
    expect(fetchAt).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(fetchAt);
  });

  it("is NOT placed in the unreachable pipeline_cancelled/pipeline_failed switch arm", () => {
    // `pipeline_cancelled` and `pipeline_failed` are both members of
    // `pipelineTypes`, and that branch `return`s before the switch — so the
    // `case "pipeline_cancelled": case "pipeline_failed":` arm is DEAD CODE and a
    // fix applied there would silently do nothing.
    const armStart = pageSource.indexOf('case "pipeline_cancelled":');
    expect(armStart).toBeGreaterThan(-1);
    const armEnd = pageSource.indexOf('case "step": {', armStart);
    expect(armEnd).toBeGreaterThan(armStart);

    // The fix must not live anywhere inside that unreachable arm.
    const armBody = pageSource.slice(armStart, armEnd);
    expect(armBody).not.toContain("applyTerminalStatus");

    // And the arm really is unreachable: both types are members of pipelineTypes,
    // whose branch `return`s before the switch is ever entered.
    const typesStart = pageSource.indexOf("const pipelineTypes = [");
    const typesEnd = pageSource.indexOf("];", typesStart);
    const typesBody = pageSource.slice(typesStart, typesEnd);
    expect(typesBody).toContain('"pipeline_cancelled"');
    expect(typesBody).toContain('"pipeline_failed"');
    expect(pageSource.indexOf("if (pipelineTypes.includes(msg.type)) {")).toBeLessThan(armStart);
  });
});
