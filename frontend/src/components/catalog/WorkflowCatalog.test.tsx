import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowSummary } from "@/lib/api";

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

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflowDefinitions: (token: string) => mockGetWorkflowDefinitions(token),
}));

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
import { WorkflowCatalog } from "./WorkflowCatalog";

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

describe("WorkflowCatalog two-gate filter + friendly label", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue(MIXED);
  });

  it("renders entitled launchables, hides non-launchable + revision/od_* rows, shows gated rows locked, and uses friendly labels", async () => {
    render(<WorkflowCatalog onSelectFeature={vi.fn()} userTier="basic" />);

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
});
