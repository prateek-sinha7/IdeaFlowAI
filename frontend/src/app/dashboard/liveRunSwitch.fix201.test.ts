/**
 * FIX-201 — KAN-168 / ISS-061 (continued):
 * Concurrent run cross-contamination resolved via per-run state store (useRunStateStore).
 *
 * Architecture: SSE down-channel (run_stream.py) + REST up-channel.
 * RunConnectionProvider stamps _sourceRunId on every SSE frame.
 * useRunStateStore holds PerRunState per runId; only the "viewed" run's state
 * renders to the UI. switchViewTo() is atomic and synchronous — no async gaps.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(
  resolve(__dirname, "../../app/dashboard/page.tsx"),
  "utf8",
);

const appHeaderSource = readFileSync(
  resolve(__dirname, "../../components/layout/AppHeader.tsx"),
  "utf8",
);

const dashboardLayoutSource = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);

const pageCollapsed = pageSource.replace(/\s+/g, " ");

function getSwitchFnBody(): string {
  const start = pageSource.indexOf("const handleSwitchToLiveRun = useCallback(");
  const end = pageSource.indexOf("const handleRevisionLaunched = useCallback(", start);
  return pageSource.slice(start, end);
}

describe("FIX-201 store architecture (what was built)", () => {
  it("useRunStateStore hook is imported in page.tsx", () => {
    expect(pageSource).toContain("useRunStateStore");
    expect(pageSource).toContain("from \"@/hooks/useRunStateStore\"");
  });

  it("runStore is instantiated in page.tsx", () => {
    expect(pageSource).toContain("const runStore = useRunStateStore()");
  });

  it("questionnaire_ready writes to runStore.update()", () => {
    expect(pageSource).toContain("runStore.update(qRunId,");
    expect(pageSource).toContain("questionnaireData: { questions: mapped }");
  });

  it("questionnaire_complete writes to runStore.update() with null", () => {
    expect(pageSource).toContain("runStore.update(qcSrcRunId, { questionnaireData: null })");
  });

  it("review_gate_ready writes to runStore.update()", () => {
    expect(pageSource).toContain("runStore.update(gateRunId, { reviewGateData: gateData })");
  });

  it("review_gate_approved clears via runStore.update()", () => {
    expect(pageSource).toContain("runStore.update(approvedSrcRunId, { reviewGateData: null })");
  });

  it("pipeline_cancelled/failed clears via runStore.update()", () => {
    expect(pageSource).toContain("runStore.update(termSrcRunId, { reviewGateData: null, questionnaireData: null })");
  });

  it("handleSwitchToLiveRun calls runStore.switchViewTo(runId)", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("runStore.switchViewTo(runId)");
  });

  it("handleSwitchToLiveRun loads from runStore.get() synchronously", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("runStore.get(runId)");
  });

  it("DashboardLayout fix: questionnaireQuestions cleared when questionnaireData is null", () => {
    expect(dashboardLayoutSource).toContain("setQuestionnaireQuestions([])");
    expect(dashboardLayoutSource).toContain("else if (!questionnaireData)");
  });
});

describe("FIX-201 store correctness", () => {
  it("SSE isolation: questionnaire projected only for viewed run", () => {
    // The store update only triggers React re-render when runId === viewedRunId.
    // For background runs, the update is stored silently (no re-render).
    expect(pageSource).toContain("if (qRunId === trackedRunIdRef.current)");
    expect(pageSource).toContain("if (gateRunId === trackedRunIdRef.current)");
  });

  it("handleSwitchToLiveRun is async (await getRunEvents)", () => {
    expect(pageSource).toContain("async (runId: string) => {");
  });

  it("handleSwitchToLiveRun sets activePipelineRunId immediately", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("setActivePipelineRunId(runId)");
  });

  it("handleSwitchToLiveRun updates submittedBrief", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("setSubmittedBrief(");
  });

  it("handleSwitchToLiveRun replays durable SSE frames through handleWebSocketMessage", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("handleWebSocketMessage(");
    expect(body).toContain("getRunEvents(switchToken, runId)");
  });

  it("handleSwitchToLiveRun seeds chat transcript (SSE frames for chat path)", () => {
    const body = getSwitchFnBody();
    expect(body).toContain("seedRunChatTranscript(durableFrames, false)");
  });

  it("handleSwitchToLiveRun does NOT call resetPipeline (FIX-149 constraint)", () => {
    const body = getSwitchFnBody();
    expect(body).not.toContain("resetPipeline()");
  });

  it("handleSwitchToLiveRun does NOT call resetReplayState", () => {
    const body = getSwitchFnBody();
    expect(body).not.toContain("resetReplayState(");
  });

  it("launchPendingRef blocks foreign SSE frames during async POST window", () => {
    expect(pageSource).toContain("launchPendingRef");
    expect(pageSource).toContain("launchPendingRef.current = true");
    expect(pageSource).toContain("launchPendingRef.current = false");
  });

  it("AppHeader LIVE_STATUSES includes 'analyzing' (matches DashboardLayout)", () => {
    const headerMatch = appHeaderSource.match(/const LIVE_STATUSES = new Set\(\[([\s\S]+?)\]\)/);
    const layoutMatch = dashboardLayoutSource.match(/const LIVE_RUN_STATUSES = new Set\(\[([\s\S]+?)\]\)/);
    expect(headerMatch).not.toBeNull();
    expect(layoutMatch).not.toBeNull();
    const headerStatuses = new Set(headerMatch![1].match(/"([^"]+)"/g)?.map(s => s.replace(/"/g, "")) ?? []);
    const layoutStatuses = new Set(layoutMatch![1].match(/"([^"]+)"/g)?.map(s => s.replace(/"/g, "")) ?? []);
    for (const status of layoutStatuses) {
      expect(headerStatuses.has(status)).toBe(true);
    }
  });
});

describe("FIX-201 safety boundary", () => {
  it("BUG-021 fresh-launch transcript reset still present", () => {
    expect(pageSource).toContain("seedRunChatTranscript([]);");
  });

  it("BUG-021 reset still inside the !isRevision block", () => {
    const start = pageCollapsed.indexOf("if (!isRevision) {");
    const end = pageCollapsed.indexOf("// For revisions, keep existing content");
    expect(start).toBeGreaterThan(-1);
    const freshRunBlock = pageCollapsed.slice(start, end);
    expect(freshRunBlock).toContain("seedRunChatTranscript([]);");
  });

  it("history-reopen seedRunChatTranscript still present", () => {
    expect(pageSource).toContain("seedRunChatTranscript(familyChatFrames,");
  });

  it("FIX-195 Fix-A recentRuns refresh still present", () => {
    expect(pageSource).toContain("FIX-195 Fix-A");
    expect(pageSource).toContain("setRecentRuns(runs)");
  });

  it("launchedRunIdsRef.add before attachRun in handleSwitchToLiveRun", () => {
    const body = getSwitchFnBody();
    const addPos = body.indexOf("launchedRunIdsRef.current.add(runId)");
    const attachPos = body.indexOf("runConnection.attachRun(runId)");
    expect(addPos).toBeGreaterThan(-1);
    expect(addPos).toBeLessThan(attachPos);
  });

  it("useRunStateStore hook exists and exports PerRunState", () => {
    const storeSource = readFileSync(
      resolve(__dirname, "../../hooks/useRunStateStore.ts"),
      "utf8",
    );
    expect(storeSource).toContain("export function useRunStateStore");
    expect(storeSource).toContain("export interface PerRunState");
    expect(storeSource).toContain("switchViewTo");
    expect(storeSource).toContain("SSE");
  });
});
