import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, fireEvent } from "@/test/renderWithProviders";
import React from "react";
import type { WorkflowSummary, UserWorkflowSummary, AnalyticsSummary } from "@/lib/api";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Mocks. Hoisted by vitest before module imports.
//
// Analog: WorkflowHistory.test.tsx (`vi.mock("@/lib/api", ...)` + the
// motion proxy that preserves the underlying HTML tag so role/text queries
// keep working). This pins the two-gate filter (user_launchable ∧
// canRunPipeline) + the friendly-label fallback deterministically, with NO
// backend — the launch-navigation assertions live in the mocked e2e.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflowDefinitions =
  vi.fn<(token: string) => Promise<WorkflowSummary[]>>();
const mockGetUserWorkflows =
  vi.fn<(token: string) => Promise<UserWorkflowSummary[]>>();
const mockCreateUserWorkflow = vi.fn();
const mockRenameUserWorkflow = vi.fn();
const mockDeleteUserWorkflow = vi.fn();
// 38-05: the owner-scoped history-average source for the per-card estimate.
// Default → empty map so the OTHER suites (which don't set it) render the
// estimate as agents-only and never reject on mount (tolerant .catch parity).
const mockGetAnalyticsSummary = vi.fn(
  async (_token?: string, _range?: string): Promise<AnalyticsSummary> =>
    ({ type_avg_duration_sec: {} } as unknown as AnalyticsSummary),
);
// 40-02: the "Jump back in" recents source (GET /api/runs list). Default →
// empty so the OTHER suites render with NO recents strip (ND-D: absent when
// there are no runs) and never reject on mount (tolerant .catch parity).
const mockGetWorkflows = vi.fn(
  async (_token?: string, _opts?: { limit?: number }): Promise<WorkflowRun[]> => [],
);

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflowDefinitions: (token: string) => mockGetWorkflowDefinitions(token),
  getUserWorkflows: (token: string) => mockGetUserWorkflows(token),
  getAnalyticsSummary: (token: string, range: string) =>
    mockGetAnalyticsSummary(token, range),
  getWorkflows: (token: string, opts?: { limit?: number }) =>
    mockGetWorkflows(token, opts),
  createUserWorkflow: (...args: unknown[]) => mockCreateUserWorkflow(...args),
  renameUserWorkflow: (...args: unknown[]) => mockRenameUserWorkflow(...args),
  deleteUserWorkflow: (...args: unknown[]) => mockDeleteUserWorkflow(...args),
}));

// A minimal WorkflowRun factory for the recents fixtures (only the fields the
// "Jump back in" strip reads matter; the rest satisfy the type).
function makeRun(partial: Partial<WorkflowRun> & { id: string }): WorkflowRun {
  return {
    title: `Run ${partial.id}`,
    type: "user_stories",
    status: "completed",
    input: "",
    parentRunId: null,
    rootRunId: partial.id,
    createdAt: new Date().toISOString(),
    agentCount: 3,
    ...partial,
  } as WorkflowRun;
}

// next/navigation router — the catalog calls useRouter() for the wizard fork.
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Same motion mock idiom used in WorkflowHistory.test.tsx — preserves the
// underlying HTML tag so role/text-based queries still find buttons.
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

// Imported AFTER the mocks so the component picks up the mocked deps.
import { HomeLaunchGrid } from "./HomeLaunchGrid";

// ─────────────────────────────────────────────────────────────────
// Fixtures — a MIXED list exercising both gates + the label fallback.
//   - user_stories      : launchable, entitled at "basic"            → SHOWN
//   - app_builder        : launchable, ABOVE "basic" (needs pro)      → SHOWN-LOCKED
//   - user_stories_revision : NOT launchable (gate 1)                 → HIDDEN
//   - od_ppt             : NOT launchable (gate 1)                    → HIDDEN
//   - custom             : launchable, NO display_name (label fallback) + above tier
// `name` on user_stories is deliberately DIFFERENT from the friendly label so
// we can assert the raw API `name` never reaches the user.
// ─────────────────────────────────────────────────────────────────

const MIXED: WorkflowSummary[] = [
  {
    id: "user_stories",
    name: "raw-user-stories-name",
    description: "Epics, user stories, and Gherkin acceptance criteria.",
    step_count: 3,
    steps: [],
    user_launchable: true,
    display_name: "Generate product requirements",
    icon: null,
    launch_surface: null,
  },
  {
    id: "app_builder",
    name: "raw-app-builder-name",
    description: "Full-stack code, tests, and infrastructure.",
    step_count: 5,
    steps: [],
    user_launchable: true,
    display_name: "Build an end-to-end application",
    icon: null,
    launch_surface: null,
  },
  {
    id: "user_stories_revision",
    name: "raw-revision-name",
    description: "Revision loop.",
    step_count: 2,
    steps: [],
    user_launchable: false,
    display_name: null,
    icon: null,
    launch_surface: null,
  },
  {
    id: "od_ppt",
    name: "raw-od-ppt-name",
    description: "On-demand deck.",
    step_count: 2,
    steps: [],
    user_launchable: false,
    display_name: null,
    icon: null,
    launch_surface: null,
  },
  {
    id: "custom",
    name: "raw-custom-name",
    description: "Assemble specialist agents.",
    step_count: 1,
    steps: [],
    user_launchable: true,
    display_name: null, // exercises the WORKFLOW_LABELS fallback ("Custom Workflow")
    icon: null,
    launch_surface: null,
  },
];

describe("HomeLaunchGrid two-gate filter + friendly label", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue(MIXED);
    mockGetUserWorkflows.mockResolvedValue([]); // no saved rows by default
  });

  it("renders entitled launchables, hides non-launchable + revision/od_* rows, shows gated rows locked, and uses friendly labels", async () => {
    renderWithProviders(<HomeLaunchGrid onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="basic" />, {
      preloadedState: {
        global: {
          workflows: MIXED,
          workflowsStatus: "succeeded",
          workflowsError: null,
          recentRuns: [],
          recentRunsStatus: "succeeded",
          recentRunsError: null,
        },
      },
    });

    // The entitled launchable shows its FRIENDLY label.
    await waitFor(() =>
      expect(
        screen.getByText("Generate product requirements"),
      ).toBeInTheDocument(),
    );

    // (a) gate 1 — a user_launchable:false row is NEVER rendered.
    expect(screen.queryByText(/Revised|user_stories_revision/i)).toBeNull();
    // od_* row (also user_launchable:false) is never rendered either.
    expect(screen.queryByText(/od_ppt|raw-od-ppt-name/i)).toBeNull();

    // (b) gate 2 — a launchable but tier-gated row is SHOWN, decorated locked
    // (not removed). "Build an end-to-end application" needs pro; tier=basic.
    expect(
      screen.getByText("Build an end-to-end application"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Requires .*plan/i).length).toBeGreaterThan(0);

    // (c) friendly-label fallback — `custom` has no display_name, so the
    // WORKFLOW_LABELS fallback ("Custom Workflow") is rendered, NOT raw `name`.
    expect(screen.getByText("Custom Workflow")).toBeInTheDocument();

    // (d) the raw API `name` is NEVER rendered as a user-facing label.
    expect(screen.queryByText("raw-user-stories-name")).toBeNull();
    expect(screen.queryByText("raw-custom-name")).toBeNull();
  });

  // WR-02: pin the label PRECEDENCE branch (display_name over getWorkflowLabel).
  // user_stories carries an explicit display_name ("Generate product
  // requirements") that differs from BOTH its raw `name` AND its friendly
  // WORKFLOW_LABELS value ("User Stories"). The explicit display_name must win;
  // the friendly-map value must NOT leak through. This is the branch the real
  // BE (now returning display_name=null, WR-01) never exercises, so without
  // this assertion an author-declared display_name could silently be ignored.
  it("renders an explicit display_name over the friendly getWorkflowLabel value (precedence)", async () => {
    renderWithProviders(<HomeLaunchGrid onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="basic" />, {
      preloadedState: {
        global: {
          workflows: MIXED,
          workflowsStatus: "succeeded",
          workflowsError: null,
          recentRuns: [],
          recentRunsStatus: "succeeded",
          recentRunsError: null,
        },
      },
    });

    // The explicit manifest display_name is shown...
    await waitFor(() =>
      expect(
        screen.getByText("Generate product requirements"),
      ).toBeInTheDocument(),
    );
    // ...and the friendly-map fallback ("User Stories" =
    // getWorkflowLabel("user_stories")) is NOT rendered for that row, proving
    // display_name takes precedence over WORKFLOW_LABELS.
    expect(screen.queryByText("User Stories")).toBeNull();

    // Conversely, the no-display_name row (`custom`) DOES fall back to the
    // friendly map ("Custom Workflow"), confirming both branches are live.
    expect(screen.getByText("Custom Workflow")).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────
// 38-05 (SC-2) — the REAL per-deliverable estimate line.
//   agents  = row.step_count (already on the WorkflowSummary wire) — ALWAYS.
//   minutes = round(type_avg_duration_sec[row.id] / 60) from the owner-scoped
//             /api/analytics/summary — rendered ONLY when a history entry for
//             that generic row id exists; otherwise the time clause is OMITTED
//             (tolerant fallback, no fabricated/hardcoded time).
//   Keyed on the generic row.id — never a workflow-name branch (SC-001).
// ─────────────────────────────────────────────────────────────────

describe("HomeLaunchGrid — real per-deliverable estimate line (SC-2, 38-05)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue(MIXED);
    mockGetUserWorkflows.mockResolvedValue([]);
    // History average covers ONE launchable row: user_stories → 300s → ~5m.
    // app_builder has NO entry → its time clause must be omitted.
    mockGetAnalyticsSummary.mockResolvedValue({
      type_avg_duration_sec: { user_stories: 300 },
    } as unknown as AnalyticsSummary);
  });

  it("shows '~N agents · ~Xm' when history exists and '~N agents' (no time) when it doesn't", async () => {
    renderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="enterprise" />,
      {
        preloadedState: {
          global: {
            workflows: MIXED,
            workflowsStatus: "succeeded",
            workflowsError: null,
            recentRuns: [],
            recentRunsStatus: "succeeded",
            recentRunsError: null,
          },
        },
      },
    );

    // WITH history — user_stories: step_count=3 → "~3 agents"; 300s/60 → "~5m".
    await waitFor(() =>
      expect(screen.getByText("~3 agents · ~5m")).toBeInTheDocument(),
    );

    // WITHOUT history — app_builder: step_count=5 → "~5 agents", NO time clause.
    expect(screen.getByText("~5 agents")).toBeInTheDocument();
    // ...and that agents-only row carries no minutes clause at all.
    expect(screen.queryByText(/~5 agents .*~\d+m/)).toBeNull();
  });

  it("keys the average on the generic row id from the owner-scoped 'all'-range summary", async () => {
    renderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="enterprise" />,
      {
        preloadedState: {
          global: {
            workflows: MIXED,
            workflowsStatus: "succeeded",
            workflowsError: null,
            recentRuns: [],
            recentRunsStatus: "succeeded",
            recentRunsError: null,
          },
        },
      },
    );

    await waitFor(() =>
      expect(screen.getByText("~3 agents · ~5m")).toBeInTheDocument(),
    );
    // Owner-scoped fetch: the endpoint enforces WHERE user_id server-side; the
    // grid asks for the full history window ("all").
    expect(mockGetAnalyticsSummary).toHaveBeenCalledWith("test-token", "all");
  });
});

// ─────────────────────────────────────────────────────────────────
// 40-02 — the shell-mock restyle: the prompt UNDER the h1 (Attach + Build, NO
// Voice — ND-X), the live-data CARD GRID (count is data-driven, ND-D), and the
// "Jump back in" recents (live GET /api/runs, absent when empty).
// ─────────────────────────────────────────────────────────────────

// A 7-launchable list — proves the card count is DATA-DRIVEN (SC-001), never
// the mock's fixed 6. Real enterprise-entitled, non-wizard ids so every card is
// allowed and clicking routes through onSelectFeature (not a router.push fork).
const SEVEN_IDS = [
  "user_stories",
  "app_builder",
  "custom",
  "migration",
  "mulesoft_to_springboot",
  "dotnet_to_azure",
  "user_stories_revision",
];
const SEVEN: WorkflowSummary[] = SEVEN_IDS.map((id, i) => ({
  id,
  name: `raw-name-${i}`,
  description: `Deliverable number ${i}.`,
  step_count: 2 + i,
  steps: [],
  user_launchable: true,
  display_name: `Deliverable ${i}`,
  icon: null,
  launch_surface: null,
}));

describe("HomeLaunchGrid — 40-02 live-data card grid (ND-D)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetUserWorkflows.mockResolvedValue([]);
  });

  it("renders one card per live launchable row (7 rows → 7 cards, not the mock's fixed 6)", async () => {
    mockGetWorkflowDefinitions.mockResolvedValue(SEVEN);
    renderWithProviders(<HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" />, {
      preloadedState: {
        global: {
          workflows: SEVEN,
          workflowsStatus: "succeeded",
          workflowsError: null,
          recentRuns: [],
          recentRunsStatus: "succeeded",
          recentRunsError: null,
        },
      },
    });

    await waitFor(() =>
      expect(screen.getByText("Deliverable 0")).toBeInTheDocument(),
    );
    // Each deliverable card carries an <h2> label — count them.
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings).toHaveLength(7);
    expect(screen.getByText("Deliverable 6")).toBeInTheDocument();
  });

  it("clicking a deliverable card launches its run (onSelectFeature with the row id)", async () => {
    const onSelectFeature = vi.fn();
    mockGetWorkflowDefinitions.mockResolvedValue(SEVEN);
    renderWithProviders(<HomeLaunchGrid onSelectFeature={onSelectFeature} userTier="enterprise" />, {
      preloadedState: {
        global: {
          workflows: SEVEN,
          workflowsStatus: "succeeded",
          workflowsError: null,
          recentRuns: [],
          recentRunsStatus: "succeeded",
          recentRunsError: null,
        },
      },
    });

    await waitFor(() =>
      expect(screen.getByText("Deliverable 3")).toBeInTheDocument(),
    );
    // The card is a <button> holding the <h2> — click it via its label.
    const card = screen
      .getAllByRole("button")
      .find((b) => b.querySelector("h2")?.textContent === "Deliverable 3");
    expect(card).toBeTruthy();
    fireEvent.click(card!);
    expect(onSelectFeature).toHaveBeenCalledWith("migration"); // SEVEN_IDS[3]
  });
});

describe("HomeLaunchGrid — 40-02 'Jump back in' recents (live GET /api/runs)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue(MIXED);
    mockGetUserWorkflows.mockResolvedValue([]);
  });

  it("renders a recent card per live run and deep-links on click", async () => {
    const onOpenRun = vi.fn();
    const recentRuns = [
      makeRun({ id: "r1", title: "Growth dashboard prototype", status: "completed" }),
      makeRun({ id: "r2", title: "Refunds backlog", status: "failed" }),
      makeRun({ id: "r3", title: "Board pitch deck", status: "running" }),
    ];
    mockGetWorkflows.mockResolvedValue(recentRuns);
    renderWithProviders(
      <HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" onOpenRun={onOpenRun} />,
      {
        preloadedState: {
          global: {
            workflows: MIXED,
            workflowsStatus: "succeeded",
            workflowsError: null,
            recentRuns: recentRuns,
            recentRunsStatus: "succeeded",
            recentRunsError: null,
          },
        },
      },
    );

    await waitFor(() =>
      expect(screen.getByText("Jump back in")).toBeInTheDocument(),
    );
    expect(screen.getByText("Growth dashboard prototype")).toBeInTheDocument();
    expect(screen.getByText("Refunds backlog")).toBeInTheDocument();
    expect(screen.getByText("Board pitch deck")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Refunds backlog"));
    expect(onOpenRun).toHaveBeenCalledTimes(1);
    expect(onOpenRun.mock.calls[0][0].id).toBe("r2");
  });

  it("omits the recents strip entirely when there are no runs (ND-D — no fabricated placeholder)", async () => {
    mockGetWorkflows.mockResolvedValue([]);
    renderWithProviders(<HomeLaunchGrid onSelectFeature={vi.fn()} userTier="enterprise" />, {
      preloadedState: {
        global: {
          workflows: MIXED,
          workflowsStatus: "succeeded",
          workflowsError: null,
          recentRuns: [],
          recentRunsStatus: "succeeded",
          recentRunsError: null,
        },
      },
    });

    await waitFor(() =>
      expect(screen.getByText("Generate product requirements")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Jump back in")).toBeNull();
  });
});
