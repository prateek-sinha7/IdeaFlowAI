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
// ISS-898: prefix anchors (no closing paren), so the ISS-304 tokenUsage args cannot stale them.
// Never shorten to a bare `applyTerminalStatus(` — its first hit is the FIX-201 bridge call, ahead of the reopen fetch.
const APPLY_CALL = "applyTerminalStatus(prev, fullRun.status";
const RECONCILE_CALL = "reconcileTerminalStatus(fullRun.status";

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
    expect(pageSource).toContain(APPLY_CALL);
  });

  it("reconciles BOTH containers — the store AND the legacy reducer state", () => {
    // PROVEN IN A BROWSER, not reasoned about: patching only the store is
    // TRANSIENT. The FIX-201 bridge (page.tsx:1663-1672) copies the legacy
    // useWorkflow.pipelineState into the store WHOLESALE once the viewport
    // switches to the reopened run, and that legacy state accumulated the same
    // terminal-less replay — so it clobbered the store patch a few hundred ms
    // later and the screen kept showing a live Stop.
    expect(pageSource).toContain(RECONCILE_CALL);
    expect(pageSource).toMatch(/reconcileTerminalStatus\s*\}\s*=\s*useWorkflow\(\)|reconcileTerminalStatus\s*\}\s*=/);
  });

  it("clears the lingering clarify panel — the one branch not gated on isRunning", () => {
    // laneClarifyOpen (DashboardLayout:1862) is deliberately NOT AND-ed with
    // isRunning, because clarify precedes pipeline_start. So resolving isRunning
    // alone leaves the header reading "Clarifying" with Stop still armed.
    expect(pageSource).toContain("runStore.update(fullRun.id, { questionnaireData: null });");
  });

  it("does NOT clear reviewGateData — that would erase the historical gate card", () => {
    const call = pageSource.indexOf(APPLY_CALL);
    expect(call).toBeGreaterThan(-1);
    const windowAfter = pageSource.slice(call, call + 1600);
    expect(windowAfter).not.toContain("reviewGateData: null");
  });

  it("writes to the run STORE — the state the UI actually reads", () => {
    // page.tsx:2494 `displayedPipelineState = runStore.viewed.pipelineState` is
    // what DashboardLayout receives. The legacy React setters at :1197-1201 are
    // NOT read by the lane, so writing there would be invisible.
    expect(pageSource).toContain("const displayedPipelineState = runStore.viewed.pipelineState;");
    const call = pageSource.indexOf(APPLY_CALL);
    const storeWrite = pageSource.lastIndexOf("runStore.updatePipelineState(", call);
    expect(storeWrite).toBeGreaterThan(-1);
  });

  // Finished-run reopen (D2): the reopen handler now awaits ONE loaded trace
  // (`loadReopenTrace`) and applies it in a single synchronous block.
  const FETCH_ANCHOR = "const reopenTrace = await loadReopenTrace();";
  const LOOP_ANCHOR = "for (const frame of reopenTrace.frames)";
  const HYDRATE_CALL = "applyAgentOutputs(prev, reopenTrace.agentOutputRows";
  const BATCH_END = "setIsLoadingRunTrace(false)";

  it("runs AFTER the durable replay loop, never before it", () => {
    // ISS-1010: search from the reopen handler's fetch — the first loop in the file is the run-switch handler's.
    const fetchAt = pageSource.indexOf(FETCH_ANCHOR);
    expect(fetchAt).toBeGreaterThan(-1);
    const loopStart = pageSource.indexOf("for (const frame of reopenTrace.frames)", fetchAt);
    const call = pageSource.indexOf(APPLY_CALL);
    expect(loopStart).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(loopStart);
  });

  it("stays inside the reopen handler, after the durable fetch", () => {
    const fetchAt = pageSource.indexOf(FETCH_ANCHOR);
    const call = pageSource.indexOf(APPLY_CALL);
    expect(fetchAt).toBeGreaterThan(-1);
    expect(call).toBeGreaterThan(fetchAt);
  });

  it("hydrates the persisted agent outputs between the replay loop and the terminal reconcile", () => {
    // D3: hydrating before the loop would be wiped by the replayed agent_start
    // resets, so it must follow the replay and precede the terminal reconcile.
    const fetchAt = pageSource.indexOf(FETCH_ANCHOR);
    const loopStart = pageSource.indexOf(LOOP_ANCHOR, fetchAt);
    const hydrate = pageSource.indexOf(HYDRATE_CALL, loopStart);
    const call = pageSource.indexOf(APPLY_CALL, loopStart);
    expect(loopStart).toBeGreaterThan(-1);
    expect(hydrate).toBeGreaterThan(loopStart);
    expect(call).toBeGreaterThan(hydrate);
  });

  it("applies the loaded trace in one synchronous block (no await between replay and the end of loading)", () => {
    // D2: an await inside the block would let React commit a half-applied
    // finished run (isRunning true, partial steps), which is the tab-bounce bug.
    const fetchAt = pageSource.indexOf(FETCH_ANCHOR);
    const loopStart = pageSource.indexOf(LOOP_ANCHOR, fetchAt);
    const batchEnd = pageSource.indexOf(BATCH_END, loopStart);
    expect(loopStart).toBeGreaterThan(-1);
    expect(batchEnd).toBeGreaterThan(loopStart);
    expect(pageSource.slice(loopStart, batchEnd)).not.toContain("await ");
  });

  it("resets the replay state and registers the run before the record fetch starts", () => {
    // D1: with the run registered first, no early event page is dropped as
    // foreign (and marked applied), and no applied page is wiped by a late reset.
    const start = pageSource.indexOf("const handleSelectWorkflowRun = useCallback(");
    expect(start).toBeGreaterThan(-1);
    const recordFetch = pageSource.indexOf("getWorkflow(currentToken, run.id, false)", start);
    const reset = pageSource.indexOf("resetPipeline();", start);
    const register = pageSource.indexOf("launchedRunIdsRef.current.add(run.id)", start);
    expect(recordFetch).toBeGreaterThan(-1);
    expect(reset).toBeGreaterThan(-1);
    expect(register).toBeGreaterThan(-1);
    expect(reset).toBeLessThan(recordFetch);
    expect(register).toBeLessThan(recordFetch);
  });

  it("deleted the formerly-unreachable pipeline_cancelled/pipeline_failed switch arm (ISS-139)", () => {
    expect(pageSource).not.toMatch(/case "pipeline_cancelled":\s*\n\s*case "pipeline_failed":/);
    const typesStart = pageSource.indexOf("const pipelineTypes = [");
    const typesEnd = pageSource.indexOf("];", typesStart);
    const typesBody = pageSource.slice(typesStart, typesEnd);
    expect(typesBody).toContain('"pipeline_cancelled"');
    expect(typesBody).toContain('"pipeline_failed"');
    const liveBlockStart = pageSource.indexOf('if (msg.type === "pipeline_cancelled" || msg.type === "pipeline_failed") {');
    expect(liveBlockStart).toBeGreaterThan(-1);
    expect(pageSource.indexOf("if (pipelineTypes.includes(msg.type)) {")).toBeLessThan(liveBlockStart);
    const liveBlockEnd = pageSource.indexOf("\n      return;\n", liveBlockStart);
    const liveBlockBody = pageSource.slice(liveBlockStart, liveBlockEnd);
    expect(liveBlockBody).toContain("runStore.update(frameRunId, { questionnaireData: null })");
  });
});

// ISS-870 — page.tsx's live allowlist must route hook_run to the reducer.
describe("page.tsx pipelineTypes includes hook_run (ISS-870)", () => {
  it("lists hook_run", () => {
    const start = pageSource.indexOf("const pipelineTypes = [");
    const body = pageSource.slice(start, pageSource.indexOf("];", start));
    expect(body).toContain('"hook_run"');
  });
});
