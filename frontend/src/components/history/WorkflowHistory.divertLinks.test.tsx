/**
 * R-20 (014-conditional-gates, T38) — the diverted-run <-> triggered-run
 * linked-cards treatment. Per contracts/sse-pipeline-diverted.md's consumer
 * contract, this covers the HISTORICAL case specifically: reconstructed
 * purely from persisted `WorkflowRun.status === "diverted"` + `parentRunId`,
 * buildable and testable independently of Phase 4's `pipeline_diverted`
 * SSE event (T32, not yet emitted by the backend as of this test).
 *
 * Scaffold cloned from WorkflowHistory.grouping.test.tsx (pure-helper +
 * rendered pattern) and WorkflowHistory.openRun.test.tsx (onOpenRun click
 * assertions).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: () => Promise.resolve(),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  getRunSummary: () => Promise.reject(new Error("no summary in this suite")),
}));
vi.mock("./RunDetailPage", () => ({
  RunDetailPage: () => <div data-testid="run-detail-page" />,
}));
vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("@/components/preview/UserStoryPreview", () => ({ UserStoryPreview: () => <div /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("@/components/preview/AppBuilderPreview", () => ({ AppBuilderPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div />,
  deriveDeliverableFilename: () => "deliverable",
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: vi.fn(() => null),
  }),
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

import { WorkflowHistory } from "./WorkflowHistory";
import { buildDivertLinks, groupRunsByFamily } from "./RevisionFamilyView";

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run",
    title: "A run",
    type: "prototype",
    status: "completed",
    input: "brief",
    output: "<html>x</html>",
    createdAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
    duration: 100,
    agentCount: 1,
    parentRunId: null,
    rootRunId: "run",
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
});

describe("buildDivertLinks (R-20 historical case) — pure", () => {
  it("links a diverted run to its parentRunId-pointing target in both directions", () => {
    const source = makeRun({ id: "run-a", status: "diverted", rootRunId: "run-a" });
    const target = makeRun({ id: "run-b", parentRunId: "run-a", rootRunId: "run-a" });
    const links = buildDivertLinks([source, target]);
    expect(links.get("run-a")).toEqual({ direction: "source", other: target });
    expect(links.get("run-b")).toEqual({ direction: "target", other: source });
  });

  it("degrades gracefully — no link when the target run is outside the loaded page", () => {
    const source = makeRun({ id: "run-a", status: "diverted", rootRunId: "run-a" });
    const links = buildDivertLinks([source]);
    expect(links.size).toBe(0);
  });

  it("does not link runs whose status is a non-divert terminal state", () => {
    const parent = makeRun({ id: "run-a", status: "completed", rootRunId: "run-a" });
    const child = makeRun({ id: "run-b", parentRunId: "run-a", rootRunId: "run-a" });
    expect(buildDivertLinks([parent, child]).size).toBe(0);
  });

  it("populates the target link's stepId from the source run's diverted_at_step_id", () => {
    const source = makeRun({ id: "run-a", status: "diverted", rootRunId: "run-a", divertedAtStepId: "step-3" });
    const target = makeRun({ id: "run-b", parentRunId: "run-a", rootRunId: "run-a" });
    const links = buildDivertLinks([source, target]);
    expect(links.get("run-b")?.stepId).toBe("step-3");
  });

  it("leaves the target link's stepId undefined when diverted_at_step_id is null", () => {
    const source = makeRun({ id: "run-a", status: "diverted", rootRunId: "run-a", divertedAtStepId: null });
    const target = makeRun({ id: "run-b", parentRunId: "run-a", rootRunId: "run-a" });
    const links = buildDivertLinks([source, target]);
    expect(links.get("run-b")?.stepId).toBeUndefined();
  });

  it("handles multiple independent divert chains in the same page", () => {
    const a = makeRun({ id: "a", status: "diverted", rootRunId: "a" });
    const b = makeRun({ id: "b", parentRunId: "a", rootRunId: "a" });
    const c = makeRun({ id: "c", status: "diverted", rootRunId: "c" });
    const d = makeRun({ id: "d", parentRunId: "c", rootRunId: "c" });
    const links = buildDivertLinks([a, b, c, d]);
    expect(links.get("a")?.other.id).toBe("b");
    expect(links.get("b")?.other.id).toBe("a");
    expect(links.get("c")?.other.id).toBe("d");
    expect(links.get("d")?.other.id).toBe("c");
  });
});

describe("groupRunsByFamily — divert boundary (R-20) — pure", () => {
  it("a divert target is its OWN family root, never merged with the diverting run's revision family", () => {
    // rootRunId mimics the backend's revision-genealogy walk, which is oblivious
    // to divert semantics — it would naively point B at A's root, same as a
    // normal revision. familyRootFor must override this by detecting A's
    // "diverted" status and stopping the walk there.
    const a = makeRun({ id: "a", status: "diverted", rootRunId: "a" });
    const b = makeRun({ id: "b", parentRunId: "a", rootRunId: "a" });
    const groups = groupRunsByFamily([a, b]);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.root.id).sort()).toEqual(["a", "b"]);
  });

  it("an ordinary revision (non-diverted parent) still merges into one family, unaffected", () => {
    const a = makeRun({ id: "a", status: "completed", rootRunId: "a" });
    const b = makeRun({ id: "b", parentRunId: "a", rootRunId: "a", type: "prototype_revision" });
    const groups = groupRunsByFamily([a, b]);
    expect(groups).toHaveLength(1);
    expect(groups[0].members).toHaveLength(2);
  });
});

describe("WorkflowHistory — R-20 linked-cards rendering (historical case)", () => {
  it("renders 'Diverted to X ->' on the source card and '<- Continued from X, step S' on the target card, each opening the other", async () => {
    const source = makeRun({ id: "run-a", title: "Run A", status: "diverted", rootRunId: "run-a", divertedAtStepId: "step-3" });
    const target = makeRun({ id: "run-b", title: "Run B", parentRunId: "run-a", rootRunId: "run-a" });
    mockGetWorkflows.mockResolvedValue({ runs: [source, target], total: 2 });
    const onOpenRun = vi.fn();
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} onOpenRun={onOpenRun} />);

    const divertedBadge = await screen.findByText("Diverted to Run B →");
    const continuedBadge = await screen.findByText(/Continued from Run A/);
    // T41/T42: diverted_at_step_id is now persisted + threaded through — the
    // clause must be included when present, not omitted.
    expect(continuedBadge.textContent).toBe("← Continued from Run A, step step-3");

    await userEvent.click(divertedBadge);
    await waitFor(() => expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ id: "run-b" })));

    onOpenRun.mockClear();
    await userEvent.click(continuedBadge);
    await waitFor(() => expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ id: "run-a" })));
  });

  it("omits the step clause when diverted_at_step_id is genuinely null (pre-migration historical row)", async () => {
    const source = makeRun({ id: "run-a", title: "Run A", status: "diverted", rootRunId: "run-a", divertedAtStepId: null });
    const target = makeRun({ id: "run-b", title: "Run B", parentRunId: "run-a", rootRunId: "run-a" });
    mockGetWorkflows.mockResolvedValue({ runs: [source, target], total: 2 });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} onOpenRun={vi.fn()} />);

    const continuedBadge = await screen.findByText(/Continued from Run A/);
    expect(continuedBadge.textContent).toBe("← Continued from Run A");
  });

  it("clicking the divert badge does not ALSO open the badge's own row (stopPropagation)", async () => {
    const source = makeRun({ id: "run-a", title: "Run A", status: "diverted", rootRunId: "run-a" });
    const target = makeRun({ id: "run-b", title: "Run B", parentRunId: "run-a", rootRunId: "run-a" });
    mockGetWorkflows.mockResolvedValue({ runs: [source, target], total: 2 });
    const onOpenRun = vi.fn();
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} onOpenRun={onOpenRun} />);

    const divertedBadge = await screen.findByText("Diverted to Run B →");
    await userEvent.click(divertedBadge);
    await waitFor(() => expect(onOpenRun).toHaveBeenCalledTimes(1));
    expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ id: "run-b" }));
  });

  it("a non-diverted run renders no divert badge", async () => {
    const run = makeRun({ id: "run-a", title: "Plain Run", status: "completed" });
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Plain Run");
    expect(screen.queryByText(/Diverted to/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Continued from/)).not.toBeInTheDocument();
  });
});
