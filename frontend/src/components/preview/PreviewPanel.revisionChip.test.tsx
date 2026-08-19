import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { RunFamily, WorkflowRun } from "@/types/index";
// ─────────────────────────────────────────────────────────────────
// C-FLAG-1 + C-FLAG-2 (260703-174) — the LIVE mount now computes
// revisionParentVersion (1-based family index of the active run's PARENT) +
// originalBriefRootRunId (revision-only root_id) from runFamily and threads both
// to the AgentThinkingTab mount, so the StartingPointCard "revision of v{n}" chip
// and "Original brief (v1)" expander actually render on a live revision run.
//
// Cloned from PreviewPanel.versionChip.test.tsx BUT — critically — this spec does
// NOT stub @/components/results/AgentThinkingTab: it renders the REAL card so the
// live-mount computation is observable (the versionChip spec stubs it, so no other
// spec can see this). Child preview components stay stubbed.
// ─────────────────────────────────────────────────────────────────
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
}));
// Strip animation-only props so role/text queries still find rendered nodes.
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
// Cheap markers for the heavy bespoke preview children — but NOT AgentThinkingTab,
// which is the real card whose live-mount computation is under test.
vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string): string => {
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      if (content) {
        const h = content.match(/^#\s+(.+)/m);
        return h ? `${h[1].toLowerCase().replace(/[^a-z0-9\s]/g, "").trim().replace(/\s+/g, "-")}.md` : "user-stories.md";
      }
      return fallback || "user-stories.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      if (content) {
        const t = content.match(/<title>([^<]+)<\/title>/i);
        const h1 = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
        if (t && t[1] !== "Presentation") return `${t[1].toLowerCase()}.html`;
        if (h1) return `${h1[1].toLowerCase()}.html`;
        return "presentation.html";
      }
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      if (content) {
        const t = content.match(/<title>(.+?)<\/title>/i);
        return t ? `${t[1].toLowerCase().replace(/[^a-z0-9\s]/g, "").trim().replace(/\s+/g, "-")}.html` : "prototype.html";
      }
      return fallback || "prototype.html";
    }
    return fallback || "deliverable";
  },
}));
import { PreviewPanel } from "./PreviewPanel";
const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
const t2 = new Date("2026-05-12T12:00:00Z").toISOString();
const M = [
  { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
  { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  { id: "r2", type: "prototype_revision", title: "v3", status: "completed", revision_index: 2, parent_run_id: "r1", created_at: t2, completed_at: t2 },
] as const;
const family3: RunFamily = { root_id: "root", members: [M[0], M[1], M[2]] };
const REVISION_INPUT = "=== REVISION REQUEST ===\nmake the header blue\n=== END REQUEST ===";
beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunFamily.mockReset();
});
describe("Live StartingPointCard revision wiring (C-FLAG-1/2) — PreviewPanel", () => {
  it("a live revision run (r2 → parent r1) renders 'revision of v2' + the Original-brief expander", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>latest</html>"
        runFamily={family3}
        liveRunId="r2"
        runInput={REVISION_INPUT}
      />,
    );
    // Reach the Steps tab (Phase 32 plan 07 relabel of "Thinking") → the REAL
    // AgentThinkingTab mounts StartingPointCard.
    fireEvent.click(screen.getByText("Steps"));
    // Active r2's parent is r1 (family index 1) → 1-based v2 → "revision of v2".
    await waitFor(() => expect(screen.getByText(/revision of v2/i)).toBeInTheDocument());
    // originalBriefRootRunId threaded (revision member) → Original-brief expander present.
    expect(screen.getByRole("button", { name: /original brief version 1/i })).toBeInTheDocument();
  });
  it("a live ROOT run (parent null) renders NO revision chip", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>latest</html>"
        runFamily={family3}
        liveRunId="root"
        runInput={REVISION_INPUT}
      />,
    );
    fireEvent.click(screen.getByText("Steps"));
    // The Starting-point card renders, but with no parent there is no chip.
    await waitFor(() => expect(screen.getByText("Revision request")).toBeInTheDocument());
    expect(screen.queryByText(/revision of v/i)).toBeNull();
  });
});
