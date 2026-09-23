import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { RunFamily, WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// ISS-154 — switching the in-family version picker to an OLDER,
// non-latest revision whose `.output` is NULL (a pre-FIX-250 row) must
// not show the neutral "Output will appear here" placeholder — that copy
// reads as if the run never produced anything, which is misleading for a
// COMPLETED, non-degraded run. Scaffold cloned from
// PreviewPanel.versionChip.test.tsx (id-keyed getWorkflow mock).
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
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
  deriveDeliverableFilename: () => "prototype.html",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const t0 = new Date("2026-08-13T10:00:00Z").toISOString();
const t1 = new Date("2026-08-13T11:00:00Z").toISOString();

// v1 ("root") is a pre-FIX-250 completed run whose `.output` is NULL — the
// exact shape the card reproduced (8a970205-... in SSEPROOFDROP).
const family2: RunFamily = {
  root_id: "root",
  members: [
    { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
    { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  ] as never,
};

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunFamily.mockReset();
});

describe("ISS-154 — older-version null-output preview", () => {
  it.fails("ISS-154 — selecting an older completed revision with a NULL .output does not fall back to the neutral 'Output will appear here' placeholder", async () => {
    mockGetWorkflow.mockImplementation((_t, id) =>
      Promise.resolve({ id, status: "completed", output: null } as unknown as WorkflowRun),
    );

    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family2} liveRunId="r1" />);

    fireEvent.click(screen.getByLabelText(/Version v2/));
    const options = screen.getAllByRole("option");
    fireEvent.click(options[0]); // v1 = "root", the null-output revision

    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    // The read-only banner confirms the older version loaded.
    await screen.findByRole("status");

    // BUG (ISS-154): this generic placeholder reads as "the run never
    // produced anything", which is wrong for a completed, non-degraded run
    // whose deliverable simply predates FIX-250's output backfill.
    expect(screen.queryByText("Output will appear here")).toBeNull();
  });
});
