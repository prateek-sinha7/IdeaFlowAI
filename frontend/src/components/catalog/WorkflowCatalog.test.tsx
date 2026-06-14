import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowSummary, UserWorkflowSummary } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Mocks. Hoisted by vitest before module imports.
//
// Analog: WorkflowHistory.test.tsx (`vi.mock("@/lib/api", ...)` + the
// motion proxy that preserves the underlying HTML tag so role/text queries
// keep working). This pins the two-gate filter (user_launchable ∧
// canRunPipeline) + the friendly-label fallback deterministically, with NO
// backend — the launch-navigation assertions live in the mocked e2e.
//
// Phase 21 adds the second list (getUserWorkflows) + the saved-row CRUD
// fetchers, so the "Your workflows" section + kebab render deterministically.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflowDefinitions =
  vi.fn<(token: string) => Promise<WorkflowSummary[]>>();
const mockGetUserWorkflows =
  vi.fn<(token: string) => Promise<UserWorkflowSummary[]>>();
const mockCreateUserWorkflow = vi.fn();
const mockRenameUserWorkflow = vi.fn();
const mockDeleteUserWorkflow = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflowDefinitions: (token: string) => mockGetWorkflowDefinitions(token),
  getUserWorkflows: (token: string) => mockGetUserWorkflows(token),
  createUserWorkflow: (...args: unknown[]) => mockCreateUserWorkflow(...args),
  renameUserWorkflow: (...args: unknown[]) => mockRenameUserWorkflow(...args),
  deleteUserWorkflow: (...args: unknown[]) => mockDeleteUserWorkflow(...args),
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
    mockGetUserWorkflows.mockResolvedValue([]); // no saved rows by default
  });

  it("renders entitled launchables, hides non-launchable + revision/od_* rows, shows gated rows locked, and uses friendly labels", async () => {
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="basic" />);

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
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="basic" />);

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
// Phase 21 — the "Your workflows" section + per-row kebab (CRUD-OWNER-SCOPED).
//   - saved rows render their OWN name (user rows, never the manifest rule);
//   - each saved row exposes a Rename/Duplicate/Delete kebab;
//   - built-in manifest rows do NOT (read-only, UI-SPEC §4);
//   - Delete → confirm → deleteUserWorkflow called + row optimistically removed.
// ─────────────────────────────────────────────────────────────────

const SAVED: UserWorkflowSummary[] = [
  {
    id: "uw-1",
    name: "My saved workflow",
    description: "A custom composition.",
    base_pipeline_type: "custom",
    agent_ids: ["a1", "a2"],
    model_overrides: null,
  },
];

describe("WorkflowCatalog — 'Your workflows' section + kebab (Phase 21)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetWorkflowDefinitions.mockResolvedValue(MIXED);
    mockGetUserWorkflows.mockResolvedValue(SAVED);
    mockDeleteUserWorkflow.mockResolvedValue(undefined);
  });

  it("renders the saved row's own name under a 'Your workflows' heading", async () => {
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="enterprise" />);

    await waitFor(() =>
      expect(screen.getByText("Your workflows")).toBeInTheDocument(),
    );
    // The saved row renders its OWN name (not a friendly-label remap).
    expect(screen.getByText("My saved workflow")).toBeInTheDocument();
  });

  it("launches a saved workflow via onLaunchSaved when its row is clicked", async () => {
    const onLaunchSaved = vi.fn();
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={onLaunchSaved} userTier="enterprise" />);

    const row = await screen.findByText("My saved workflow");
    await userEvent.click(row);
    expect(onLaunchSaved).toHaveBeenCalledTimes(1);
    expect(onLaunchSaved.mock.calls[0][0]).toMatchObject({ id: "uw-1" });
  });

  it("exposes a Rename/Duplicate/Delete kebab on a saved row but not on built-in rows", async () => {
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="enterprise" />);

    await screen.findByText("My saved workflow");

    // Built-in rows are read-only — the kebab menu items never appear for them
    // until a kebab is opened. There is exactly ONE kebab toggle (the saved row).
    // Open it and assert the three actions appear.
    const buttons = screen.getAllByRole("button");
    // The kebab toggle is the icon-only button inside the saved-row's relative
    // container; opening any kebab reveals the three items. Find + click it.
    // (Built-in rows render an ArrowRight/Lock, NOT a MoreHorizontal toggle.)
    // Click each button until the menu opens (deterministic: only one toggles it).
    for (const b of buttons) {
      await userEvent.click(b);
      if (screen.queryByText("Rename")) break;
    }

    expect(screen.getByText("Rename")).toBeInTheDocument();
    expect(screen.getByText("Duplicate")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("Delete → confirm calls deleteUserWorkflow and optimistically removes the row", async () => {
    render(<WorkflowCatalog onSelectFeature={vi.fn()} onLaunchSaved={vi.fn()} userTier="enterprise" />);

    await screen.findByText("My saved workflow");

    // Open the kebab.
    for (const b of screen.getAllByRole("button")) {
      await userEvent.click(b);
      if (screen.queryByText("Delete")) break;
    }
    // Click "Delete" in the menu → confirm modal opens.
    await userEvent.click(screen.getByText("Delete"));
    // The confirm modal's primary action is the gray-900 "Delete" button.
    const confirmButtons = screen.getAllByText("Delete");
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => expect(mockDeleteUserWorkflow).toHaveBeenCalledTimes(1));
    expect(mockDeleteUserWorkflow.mock.calls[0][1]).toBe("uw-1");
    // Optimistically removed from the list.
    await waitFor(() =>
      expect(screen.queryByText("My saved workflow")).toBeNull(),
    );
  });
});
