import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import React from "react";
import type { WorkflowRun } from "@/types/index";
import { renderWithProviders } from "@/test/renderWithProviders";
// ─────────────────────────────────────────────────────────────────
// SHELL-02 — History Today/Earlier/Older grouping + tokens/duration sort.
// The date buckets + the sort layer OVER the existing family grouping,
// derived entirely from fields already on each list row (created_at for the
// bucket; duration + token_usage.total_tokens for the sort) — NO backend
// change, NO new fetch. Families stay intact (a family card matches if ANY
// member matches). Pure-helper assertions + a rendered-DOM ordering assert.
// Scaffold cloned from WorkflowHistory.family.test.tsx.
// ─────────────────────────────────────────────────────────────────
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  // Detail (RunDetailPage) is not mounted by these list-view tests, but the
  // symbol must exist so the WorkflowHistory→RunDetailPage import resolves.
  getRunSummary: () => Promise.resolve(null),
}));
vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("@/components/preview/UserStoryPreview", () => ({ UserStoryPreview: () => <div /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    // Simple stub: return fallback or a type-based default
    if (fallback) return fallback;
    if (workflowType.includes("user_stories")) return "user-stories.md";
    if (workflowType.includes("ppt")) return "presentation.html";
    if (workflowType.includes("prototype")) return "prototype.html";
    if (workflowType.includes("app_builder")) return "project.zip";
    if (workflowType === "custom") return "custom-output.md";
    return "deliverable";
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
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
import { WorkflowHistory } from "./WorkflowHistory";
import {
  bucketAndSortFamilies,
  dateBucketOf,
  groupRunsByFamily,
} from "./RevisionFamilyView";
const DAY = 86_400_000;
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
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
});
describe("History grouping helpers (SHELL-02) — pure", () => {
  it("dateBucketOf partitions created_at into Today / Earlier / Older", () => {
    const now = new Date("2026-07-09T12:00:00Z");
    expect(dateBucketOf(new Date("2026-07-09T01:00:00Z").toISOString(), now)).toBe("Today");
    expect(dateBucketOf(new Date(now.getTime() - 3 * DAY).toISOString(), now)).toBe("Earlier");
    expect(dateBucketOf(new Date(now.getTime() - 30 * DAY).toISOString(), now)).toBe("Older");
  });
  it("bucketAndSortFamilies buckets by root.created_at and sorts within a bucket by the chosen key", () => {
    // LOCAL constructors, deliberately: `dateBucketOf` buckets against LOCAL
    // calendar midnight (`new Date(y, m, d)`), which is the product semantics.
    // Building these as UTC instants made the fixture wrong in any zone east of
    // UTC — e.g. at UTC+05:30, 2026-07-09T20:00Z is already July 10 locally, so
    // local midnight is 2026-07-09T18:30Z and every `today(9..12)` UTC instant
    // fell into "Earlier". Same-local-day constructors keep the intent portable.
    const now = new Date(2026, 6, 9, 20, 0, 0, 0);
    const today = (h: number) => new Date(2026, 6, 9, h, 0, 0, 0).toISOString();
    const runs = [
      makeRun({ id: "alpha", title: "Alpha", rootRunId: "alpha", createdAt: today(11), duration: 900, tokenUsage: { total_tokens: 100, total_input_tokens: 60, total_output_tokens: 40, estimated_cost_usd: 0 } }),
      makeRun({ id: "beta", title: "Beta", rootRunId: "beta", createdAt: today(9), duration: 100, tokenUsage: { total_tokens: 900, total_input_tokens: 500, total_output_tokens: 400, estimated_cost_usd: 0 } }),
      makeRun({ id: "gamma", title: "Gamma", rootRunId: "gamma", createdAt: today(12), duration: 10, tokenUsage: { total_tokens: 500, total_input_tokens: 300, total_output_tokens: 200, estimated_cost_usd: 0 } }),
    ];
    const groups = groupRunsByFamily(runs);
    const recent = bucketAndSortFamilies(groups, "recent", now);
    expect(recent).toHaveLength(1);
    expect(recent[0].bucket).toBe("Today");
    expect(recent[0].groups.map((g) => g.root.id)).toEqual(["gamma", "alpha", "beta"]);
    const tokens = bucketAndSortFamilies(groups, "tokens", now);
    expect(tokens[0].groups.map((g) => g.root.id)).toEqual(["beta", "gamma", "alpha"]);
    const duration = bucketAndSortFamilies(groups, "duration", now);
    expect(duration[0].groups.map((g) => g.root.id)).toEqual(["alpha", "beta", "gamma"]);
  });
  it("returns only non-empty buckets, ordered Today → Earlier → Older", () => {
    const now = new Date("2026-07-09T20:00:00Z");
    const runs = [
      makeRun({ id: "t", rootRunId: "t", createdAt: new Date(now.getTime() - 1 * DAY + 0).toISOString() }),
    ];
    // one run 30d ago (Older) + one today.
    runs.push(makeRun({ id: "today", rootRunId: "today", createdAt: now.toISOString() }));
    runs.push(makeRun({ id: "old", rootRunId: "old", createdAt: new Date(now.getTime() - 30 * DAY).toISOString() }));
    const sections = bucketAndSortFamilies(groupRunsByFamily(runs), "recent", now);
    expect(sections.map((s) => s.bucket)).toEqual(["Today", "Earlier", "Older"]);
  });
});
describe("History grouping — rendered (SHELL-02)", () => {
  const today = (h: number) => {
    const d = new Date();
    d.setHours(h, 0, 0, 0);
    return d.toISOString();
  };
  it("renders Today / Earlier / Older group headers and keeps revision families intact", async () => {
    const now = Date.now();
    const runs = [
      makeRun({ id: "alpha", title: "Alpha today", rootRunId: "alpha", createdAt: today(11) }),
      makeRun({ id: "earlier", title: "Earlier run", rootRunId: "earlier", createdAt: new Date(now - 3 * DAY).toISOString() }),
      makeRun({ id: "old", title: "Old run", rootRunId: "old", createdAt: new Date(now - 30 * DAY).toISOString() }),
      // A 2-member family (root today) → still ONE card with a v2 pill.
      makeRun({ id: "famroot", title: "Family root", rootRunId: "famroot", createdAt: today(8) }),
      makeRun({ id: "famrev", title: "Family rev", type: "prototype_revision", parentRunId: "famroot", rootRunId: "famroot", createdAt: today(9) }),
    ];
    mockGetWorkflows.mockResolvedValue({ runs, total: runs.length });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Alpha today");
    // Bucket headers (mock copy: "Earlier" reads "Earlier this week").
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Earlier this week")).toBeInTheDocument();
    expect(screen.getByText("Older")).toBeInTheDocument();
    // Family stays intact → exactly one v2 count pill.
    expect(screen.getByLabelText("2 versions")).toBeInTheDocument();
  });
  it("the tokens/duration sort control reorders the list deterministically within a bucket", async () => {
    const runs = [
      makeRun({ id: "alpha", title: "Alpha", rootRunId: "alpha", createdAt: today(11), duration: 900, tokenUsage: { total_tokens: 100, total_input_tokens: 60, total_output_tokens: 40, estimated_cost_usd: 0 } }),
      makeRun({ id: "beta", title: "Beta", rootRunId: "beta", createdAt: today(9), duration: 100, tokenUsage: { total_tokens: 900, total_input_tokens: 500, total_output_tokens: 400, estimated_cost_usd: 0 } }),
      makeRun({ id: "gamma", title: "Gamma", rootRunId: "gamma", createdAt: today(12), duration: 10, tokenUsage: { total_tokens: 500, total_input_tokens: 300, total_output_tokens: 200, estimated_cost_usd: 0 } }),
    ];
    mockGetWorkflows.mockResolvedValue({ runs, total: runs.length });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Alpha");
    const titleOrder = () =>
      screen
        .getAllByText(/^(Alpha|Beta|Gamma)$/)
        .map((el) => el.textContent);
    // Default = recent (newest latest-member first): Gamma(12) Alpha(11) Beta(9).
    expect(titleOrder()).toEqual(["Gamma", "Alpha", "Beta"]);
    // Sort by tokens: Beta(900) Gamma(500) Alpha(100).
    fireEvent.click(screen.getByRole("button", { name: /sort by tokens/i }));
    expect(titleOrder()).toEqual(["Beta", "Gamma", "Alpha"]);
    // Sort by duration: Alpha(900) Beta(100) Gamma(10).
    fireEvent.click(screen.getByRole("button", { name: /sort by duration/i }));
    expect(titleOrder()).toEqual(["Alpha", "Beta", "Gamma"]);
  });
});
