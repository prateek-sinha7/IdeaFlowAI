import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-055 / ISS-744 (root cause) and ISS-745 (inferred sibling) — a version
// pinned via the RunHeader VersionMenu must survive a tracked *_revision
// pipeline completing, which page.tsx:1495-1522 turns into a `liveRunId` prop
// change (and a grown `runFamily`) on THIS component. Today PreviewPanel.tsx:883
// (`useEffect(() => setViewingVersion(null), [liveRunId])`) clears the pin on
// ANY liveRunId change, unconditionally.
//
// Scaffold copied from PreviewPanel.sandboxRef.test.tsx (the CURRENT, working
// mock shape for the task-U1 RunHeader VersionMenu — real git tags via
// getRunSandboxRefs, RunHeader itself left un-mocked so its real chip/dropdown
// renders). PreviewPanel.versionChip.test.tsx was NOT used as a base: it tests
// a pre-task-U1 chip UI (`aria-label="Version vN, choose version"`) that no
// longer exists in RunHeader.tsx — every one of its 5 tests fails today for
// that unrelated, pre-existing reason (confirmed by running it), not because
// of QA-PS-055. That drift is out of scope for this card and is not touched
// here; flagged in the test-writer's notes instead.
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetRunSandboxRefs = vi.fn();
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockGetRunSandboxZip = vi.fn();
const mockResolveRunDeliverable = vi.fn();
const mockGetWorkflow = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (...args: unknown[]) => mockGetWorkflow(...args),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunSandboxRefs: (...args: unknown[]) => mockGetRunSandboxRefs(...args),
  getRunSandbox: (...args: unknown[]) => mockGetRunSandbox(...args),
  getRunSandboxFile: (...args: unknown[]) => mockGetRunSandboxFile(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => mockGetRunSandboxFileBlob(...args),
  getRunSandboxZip: (...args: unknown[]) => mockGetRunSandboxZip(...args),
  resolveRunDeliverable: (...args: unknown[]) => mockResolveRunDeliverable(...args),
}));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  downloadBlob: vi.fn(),
  deriveDeliverableFilename: () => "prototype.html",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";
import type { PipelineRunState } from "@/types/index";

const SETTLED_STATE = {
  isRunning: false,
  pipelineRunId: "run-1",
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

// Same-family fixture: v1 (root), v2 (the initially-live member).
const V1_ID = "member-uuid-v1";
const V2_ID = "member-uuid-v2";
// The revision that completes WHILE v1 is pinned (ISS-744's repro) —
// page.tsx advances liveRunId to this id and the family grows to include it.
const V3_ID = "member-uuid-v3";

const family2 = {
  root_id: V1_ID,
  members: [
    { id: V1_ID, type: "prototype", title: "v1 run", status: "completed", revision_index: 1, parent_run_id: null, created_at: "2026-09-01T00:00:00Z", completed_at: "2026-09-01T01:00:00Z", git_tag: "v1" },
    { id: V2_ID, type: "prototype", title: "v2 run", status: "completed", revision_index: 2, parent_run_id: V1_ID, created_at: "2026-09-02T00:00:00Z", completed_at: "2026-09-02T01:00:00Z", git_tag: "v2" },
  ],
};
const family3 = {
  root_id: V1_ID,
  members: [
    ...family2.members,
    { id: V3_ID, type: "prototype_revision", title: "v3 run", status: "completed", revision_index: 3, parent_run_id: V2_ID, created_at: "2026-09-03T00:00:00Z", completed_at: "2026-09-03T01:00:00Z", git_tag: "v3" },
  ],
};

// ISS-745 (inferred): an UNRELATED family — a completely different root and
// members — simulating a concurrently-tracked revision from a family that has
// nothing to do with the one currently pinned on screen.
const FOREIGN_ID = "member-uuid-foreign";
const familyForeign = {
  root_id: FOREIGN_ID,
  members: [
    { id: FOREIGN_ID, type: "prototype", title: "foreign v1", status: "completed", revision_index: 1, parent_run_id: null, created_at: "2026-09-01T00:00:00Z", completed_at: "2026-09-01T01:00:00Z", git_tag: "v1" },
  ],
};

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset().mockImplementation((_token: string, runId: string) => {
    if (runId === V1_ID) {
      return Promise.resolve({ id: V1_ID, output: "<html>v1 content</html>", agentOutputs: [], tokenUsage: null, status: "completed" });
    }
    return Promise.resolve(null);
  });
  // Tags resolve the same regardless of which run id is asked — only the
  // pin-survival mechanism is under test here, not the tag-fetch itself.
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2", "v3"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: "run-1", expired: false, truncated: false, files: [] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html>content</html>");
  mockGetRunSandboxFileBlob.mockReset();
  mockGetRunSandboxZip.mockReset();
  mockResolveRunDeliverable.mockReset().mockResolvedValue({ path: "prototype.html", size: 10, modified: 1, text: true, kind: "text", deliverable: true });
});

describe("Pin survives a tracked revision completing (QA-PS-055 / ISS-744, ISS-745 inferred)", () => {
  // Was `{ fails: true }` (xfail) pinning QA-PS-055 — went green when FIX-603
  // landed (PreviewPanel.tsx:920 now guards the reset on `!pinnedVersion`).
  it("QA-PS-055 / ISS-744 — pinning v1, then a tracked revision completing (liveRunId advances, family grows) must not silently drop the pin", async () => {
    const { rerender } = render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v2 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_ID}
        runFamily={family2}
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", V2_ID));

    // Pin v1 via the RunHeader VersionMenu (the real, current pin path).
    const chip = screen.getByRole("button", { name: /^v2\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_ID));

    const bannersBefore = screen.getAllByRole("status");
    const bannerBefore = bannersBefore.find((el) => el.textContent?.includes("read-only")) ?? bannersBefore[0];
    expect(bannerBefore.textContent).toMatch(/Viewing v1/);

    // A tracked *_revision completes: page.tsx:1521-1522's pipeline_complete
    // handler calls setContentSourceRunId(completingRunId) unconditionally for
    // any *_revision completion (isRevisionCompletion bypasses the
    // foreign-run guard), which is exactly this liveRunId/runFamily prop
    // change from PreviewPanel's point of view.
    rerender(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v3 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V3_ID}
        runFamily={family3}
      />,
    );

    // BUG: PreviewPanel.tsx:883 clears the pin on ANY liveRunId change with no
    // check that a pin is active. The v1 pin (and its read-only banner) should
    // survive; today it is silently wiped and the screen snaps to the new
    // "Latest (live)" instead.
    const bannersAfter = screen.queryAllByRole("status");
    const bannerAfter = bannersAfter.find((el) => el.textContent?.includes("read-only"));
    expect(bannerAfter).toBeDefined();
    expect(bannerAfter!.textContent).toMatch(/Viewing v1/);
  });

  it("GREEN control — with NO pin active, the same liveRunId/family advance correctly follows to latest (must keep working after the fix)", async () => {
    const { rerender } = render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v2 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_ID}
        runFamily={family2}
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", V2_ID));
    expect(screen.getByRole("button", { name: /^v2\b/ })).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();

    rerender(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v3 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V3_ID}
        runFamily={family3}
      />,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: /^v3\b/ })).toBeInTheDocument());
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("ISS-745 (INFERRED, unconfirmed) — pinning v1, then a tracked revision from an UNRELATED family completing must not redirect/drop the pin", { fails: true }, async () => {
    // Not reproduced live (ISS-745 was filed from a code-read inference, not a
    // browser observation) — this asserts the SAME PreviewPanel.tsx:883 effect
    // fires identically when liveRunId is replaced by a run id from a
    // completely different family (different root_id, no shared members),
    // which is the harder case ISS-745 describes: the screen is not merely
    // reset to its own latest, it is redirected to an unrelated family.
    const { rerender } = render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v2 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_ID}
        runFamily={family2}
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", V2_ID));

    const chip = screen.getByRole("button", { name: /^v2\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_ID));

    const bannersBefore = screen.getAllByRole("status");
    expect(bannersBefore.find((el) => el.textContent?.includes("read-only"))?.textContent).toMatch(/Viewing v1/);

    // A concurrently-tracked revision on an ENTIRELY DIFFERENT family
    // completes; page.tsx's isRevisionCompletion has no lineage check, so it
    // advances contentSourceRunId to that foreign run's id regardless.
    rerender(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>foreign live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={FOREIGN_ID}
        runFamily={familyForeign}
      />,
    );

    const bannersAfter = screen.queryAllByRole("status");
    const bannerAfter = bannersAfter.find((el) => el.textContent?.includes("read-only"));
    expect(bannerAfter).toBeDefined();
    expect(bannerAfter!.textContent).toMatch(/Viewing v1/);
  });
});
