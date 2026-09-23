/**
 * ISS-769 — sibling of ISS-722 (QA-SG-001): AppHeader's "legacy" single-run
 * badge (AppHeader.tsx:450-469, rendered when `runningPipelines.length === 0
 * && isPipelineRunning && pipelineType` — "edge case on first render") reads
 * `pipelineAgentsTotal`, which DashboardLayout computes at line 2720 as:
 *
 *   pipelineAgentsTotal={pipelineState?.agents?.length ?? 0}
 *
 * the same unguarded client-roster read ISS-722 named for StepsOverviewSpine,
 * with no fallback to the run's known `agent_count` anywhere on this path
 * (confirmed by grep — no `agentCount` identifier near this prop). Because
 * the badge only renders the count when `pipelineAgentsTotal > 0`
 * (AppHeader.tsx:464), the empty-roster window does not show a visible
 * "0/0" here — it silently omits the count instead, alongside the workflow
 * label.
 *
 * No harness mounts DashboardLayout at the exact edge case the code comment
 * names (`recentRuns` not yet populated + `pipelineState.isRunning` already
 * true) — same class of gap as ISS-649/ISS-644 in this file, so this test
 * pins the defect directly against the real prop expression rather than
 * simulating the race through a full render.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("DashboardLayout — ISS-769 legacy badge total fallback (QA-SG-001)", () => {
  it("passes AppHeader's pipelineAgentsTotal a fallback to the run's known agent_count, not just the live roster length", () => {
    const src = readFileSync(path.join(__dirname, "DashboardLayout.tsx"), "utf8");

    const match = src.match(/pipelineAgentsTotal=\{([^}]*)\}/);
    expect(match).not.toBeNull();

    // Expected/correct behaviour: the same `|| agentCount`-style fallback
    // AppHeader.tsx:216 already uses for the notification/dropdown path,
    // so the legacy badge shows the known total instead of silently
    // omitting it while the roster is still empty.
    expect(match![1]).toMatch(/agentCount/i);
  });
});
