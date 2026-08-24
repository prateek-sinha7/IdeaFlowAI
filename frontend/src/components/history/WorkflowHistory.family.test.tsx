import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import React from "react";
import renderWithProviders from "@/test/renderWithProviders";
import type { WorkflowRun, RunFamily } from "@/types/index";
import type { RunSummary } from "@/lib/api";
// ─────────────────────────────────────────────────────────────────
// Revision Families (B2 / POR §5 D3+D4): behavior specs for the history
// family grouping (Surface 1) + the detail version timeline (Surface 2).
// Real rendered-DOM asserts (never source-lock) — the B1 revise spec proves
// WorkflowHistory renders fine in vitest. Scaffold cloned from
// WorkflowHistory.revise.test.tsx, with getRunFamily added to the api mock.
// ─────────────────────────────────────────────────────────────────
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();
// SHELL-03: the detail version timeline now renders inside the single-source
// RunDetailPage (fed by getRunSummary). Controllable so the family walk drives it.
const mockGetRunSummary = vi.fn<(token: string, id: string) => Promise<RunSummary>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
  getRunSummary: (token: string, id: string) => mockGetRunSummary(token, id),
  // C2: WorkflowHistory now statically imports+calls getRunArtifacts on reopen;
  // return an empty artifact shape so ClarificationsCard renders null (no rounds)
  // and StartingPointCard renders from selectedRun.input unchanged (avoids the
  // B2 undefined-mock-export crash).
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
}));
vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content }: { content: string }) => <div data-testid="ppt-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: ({ content }: { content: string }) => <div data-testid="prototype-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    // Simple stub matching the real export's signature and behavior
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      return fallback || "user-stories.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      return fallback || "prototype.html";
    }
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") {
      return "project.zip";
    }
    return fallback || "deliverable";
  },
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
    }
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
import { WorkflowHistory } from "./WorkflowHistory";
function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "hist-7",
    title: "Interactive prototype",
    type: "prototype",
    status: "completed",
    input: "build a landing page",
    output: "<!doctype html><html><body>hello</body></html>",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: "hist-7",
    ...overrides,
  };
}
// Distinct chronological timestamps so ordering is deterministic.
const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
const t2 = new Date("2026-05-12T12:00:00Z").toISOString();
const t3 = new Date("2026-05-12T13:00:00Z").toISOString();
// A 3-member family (root + 2 revisions sharing rootRunId "root").
function familyRuns(): WorkflowRun[] {
  return [
    makeRun({ id: "root", title: "Root run", type: "prototype", parentRunId: null, rootRunId: "root", createdAt: t0, output: "<html>root</html>" }),
    makeRun({ id: "r1", title: "Rev one", type: "prototype_revision", parentRunId: "root", rootRunId: "root", createdAt: t1, output: "<html>r1</html>" }),
    makeRun({
      id: "r2", title: "Rev two", type: "prototype_revision", parentRunId: "r1", rootRunId: "root", createdAt: t2,
      input: "=== REVISION REQUEST ===\nmake the header blue",
      output: "<html>r2</html>",
    }),
  ];
}
function familyPayload(): RunFamily {
  return {
    root_id: "root",
    members: [
      { id: "root", type: "prototype", title: "Root run", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
      { id: "r1", type: "prototype_revision", title: "Rev one", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
      { id: "r2", type: "prototype_revision", title: "Rev two", status: "completed", revision_index: 2, parent_run_id: "r1", created_at: t2, completed_at: t2 },
    ],
  };
}
// The RunDetailPage summary column renders the reused VersionTimeline off the
// family walk (members). getRunSummary returns the same 3 members regardless of
// the requested version so the chip row renders for every opened member.
function summaryFor(id: string): RunSummary {
  const fam = familyPayload();
  const member = fam.members.find((m) => m.id === id) ?? fam.members[0];
  return {
    id: member.id,
    title: member.title,
    type: member.type,
    status: member.status,
    duration: null,
    agent_count: 0,
    token_usage: { total_tokens: 0 },
    error: null,
    agents: [],
    root_id: fam.root_id,
    members: fam.members,
  };
}
beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
  mockGetRunFamily.mockReset();
  mockGetRunSummary.mockReset().mockImplementation((_t, id) => Promise.resolve(summaryFor(id)));
});
describe("Revision Families (B2) — history grouping (D3)", () => {
  it("groups a multi-run family into one card with a v{N} pill; standalone stays a plain row; expand shows chronological rows with revises microcopy", async () => {
    const runs = [
      ...familyRuns(),
      makeRun({ id: "solo", title: "Solo run", type: "ppt", parentRunId: null, rootRunId: "solo", createdAt: t3, output: "<html>solo</html>" }),
    ];
    mockGetWorkflows.mockResolvedValue({ runs, total: runs.length });
    mockGetRunFamily.mockResolvedValue(familyPayload());
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    // Standalone renders as a plain row (present).
    await screen.findByText("Solo run");
    // Exactly ONE v3 count pill for the family (aria-label "3 versions").
    expect(screen.getByLabelText("3 versions")).toBeInTheDocument();
    // The family root title renders on the collapsed card.
    expect(screen.getByText("Root run")).toBeInTheDocument();
    // Child version rows are hidden until expanded.
    expect(screen.queryByText("Rev one")).toBeNull();
    // Expand the family.
    fireEvent.click(screen.getByLabelText("Show versions"));
    // Three chronological version rows appear with the revises microcopy.
    await waitFor(() => expect(screen.getByText("Rev one")).toBeInTheDocument());
    expect(screen.getByText("Rev two")).toBeInTheDocument();
    expect(screen.getByText("↳ revises v1")).toBeInTheDocument(); // rev1 revises root = v1
    expect(screen.getByText("↳ revises v2")).toBeInTheDocument(); // rev2 revises rev1 = v2
  });
  it("child version row is a native button (aria-label) that opens the version on activation (§8 keyboard)", async () => {
    const runs = familyRuns();
    mockGetWorkflows.mockResolvedValue({ runs, total: runs.length });
    mockGetRunFamily.mockResolvedValue(familyPayload());
    const byId: Record<string, WorkflowRun> = Object.fromEntries(familyRuns().map((r) => [r.id, r]));
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve(byId[id]));
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Root run");
    // Expand the family.
    fireEvent.click(screen.getByLabelText("Show versions"));
    // The child version row is a native BUTTON carrying the a11y label (v2 = "Rev one").
    const row = await screen.findByRole("button", { name: /Version 2, completed/ });
    // Activating it opens that version (onSelectRun → detail view): the family
    // fetches and the version timeline renders its radio chips.
    fireEvent.click(row);
    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3));
  });
  it("renders a single-member (standalone) family as a plain row — no pill, no expander (zero regression)", async () => {
    const solo = makeRun({ id: "solo", title: "Just me", type: "ppt", parentRunId: null, rootRunId: "solo", createdAt: t0, output: "<html>solo</html>" });
    mockGetWorkflows.mockResolvedValue({ runs: [solo], total: 1 });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Just me");
    // No expander.
    expect(screen.queryByLabelText("Show versions")).toBeNull();
    // No "v{N}" count pill.
    expect(screen.queryByLabelText(/\d+ versions/)).toBeNull();
  });
});
describe("Revision Families (B2) — detail version timeline (D4)", () => {
  async function openLatestDetail() {
    const runs = familyRuns();
    mockGetWorkflows.mockResolvedValue({ runs, total: runs.length });
    mockGetRunFamily.mockResolvedValue(familyPayload());
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    // Click the family root card body → opens the latest member (v3 = r2).
    const card = await screen.findByText("Root run");
    fireEvent.click(card);
    // Wait for the version chips to render (family fetched on open).
    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3));
  }
  it("renders 3 chronological chips and the active chip matches the loaded version", async () => {
    await openLatestDetail();
    const chips = screen.getAllByRole("radio");
    expect(chips).toHaveLength(3);
    // Opened the latest = v3 → the 3rd chip is active.
    expect(chips[2].getAttribute("aria-checked")).toBe("true");
    expect(chips[0].getAttribute("aria-checked")).toBe("false");
    // Unified lowercase microcopy: the timeline context line reads "↳ revises v{n}".
    expect(screen.getByText(/↳ revises v/)).toBeInTheDocument();
  });
  it("clicking a sibling chip re-syncs BOTH columns to that version (getWorkflow reloads the deliverable; getRunSummary refetches the summary) + the active chip follows", async () => {
    // The switch is caller-owned (WorkflowHistory.handleSelectVersion): it loads
    // the version's full run (right column) AND re-keys RunDetailPage → summary
    // refetch. Key getWorkflow by id so setSelectedRun lands the clicked member.
    const byId: Record<string, WorkflowRun> = Object.fromEntries(familyRuns().map((r) => [r.id, r]));
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve(byId[id]));
    await openLatestDetail();
    // Click the v1 sibling chip (first radio).
    fireEvent.click(screen.getAllByRole("radio")[0]);
    // Right column reloads the version's deliverable via getWorkflow …
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    // … and the RunDetailPage summary column refetches for the same version.
    await waitFor(() => expect(mockGetRunSummary).toHaveBeenCalledWith("test-token", "root"));
    // The active chip follows the loaded version → v1 checked, v3 unchecked.
    await waitFor(() => {
      const chips = screen.getAllByRole("radio");
      expect(chips[0].getAttribute("aria-checked")).toBe("true");
      expect(chips[2].getAttribute("aria-checked")).toBe("false");
    });
  });
  it("exposes the chip row as a radiogroup with radio chips carrying aria-checked (a11y)", async () => {
    await openLatestDetail();
    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    const chips = screen.getAllByRole("radio");
    expect(chips.length).toBeGreaterThanOrEqual(2);
    for (const chip of chips) {
      expect(chip.hasAttribute("aria-checked")).toBe(true);
    }
  });
});
