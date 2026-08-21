import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { UserWorkflowSummary } from "@/lib/api";
import { routes } from "@/lib/routes";

// ─────────────────────────────────────────────────────────────────
// Mocks. Hoisted by vitest before module imports.
//
// Idiom mirrors HomeLaunchGrid.test.tsx: vi.mock("@/lib/api", ...) for the
// CRUD fetchers + the motion proxy that preserves the underlying HTML tag so
// role/text/label queries keep working. This is the Wave-0 gap closure
// (36-VALIDATION): no SavedWorkflowsPage test existed. It LOCKS the D-11 label
// ("My Workflows", never "Workflow Catalogue") + the D-15 contract that the
// Rename/Duplicate/Delete kebab is REAL (wired to /api/user-workflows CRUD),
// never regressed to static text.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetUserWorkflows =
  vi.fn<(token: string) => Promise<UserWorkflowSummary[]>>();
const mockCreateUserWorkflow = vi.fn();
const mockRenameUserWorkflow = vi.fn();
const mockDeleteUserWorkflow = vi.fn();
const mockRouterPush = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getUserWorkflows: (token: string) => mockGetUserWorkflows(token),
  createUserWorkflow: (...args: unknown[]) => mockCreateUserWorkflow(...args),
  renameUserWorkflow: (...args: unknown[]) => mockRenameUserWorkflow(...args),
  deleteUserWorkflow: (...args: unknown[]) => mockDeleteUserWorkflow(...args),
}));

// Same motion mock idiom used in HomeLaunchGrid.test.tsx — preserves the
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

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockRouterPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: vi.fn(() => null),
  }),
}));

// Imported AFTER the mocks so the component picks up the mocked deps.
import { SavedWorkflowsPage } from "./SavedWorkflowsPage";

// ─────────────────────────────────────────────────────────────────
// Fixture — ONE owned saved row, so kebab/CRUD assertions are unambiguous.
// ─────────────────────────────────────────────────────────────────
const ROW: UserWorkflowSummary = {
  id: "uw-1",
  name: "My saved workflow",
  description: "A custom composition.",
  base_pipeline_type: "custom",
  agent_ids: ["a1", "a2"],
  model_overrides: null,
  updated_at: "2026-07-01T10:00:00",
};

function makeRows(): UserWorkflowSummary[] {
  return [{ ...ROW }];
}

// Open the saved row's kebab, then click a menuitem by its label.
async function openKebabAndClick(user: ReturnType<typeof userEvent.setup>, itemLabel: string) {
  const trigger = await screen.findByRole("button", { name: "Workflow actions" });
  await user.click(trigger);
  const menu = await screen.findByRole("menu");
  await user.click(within(menu).getByText(itemLabel));
}

describe("SavedWorkflowsPage — D-11 label", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetUserWorkflows.mockResolvedValue(makeRows());
  });

  it("renders the heading 'My Workflows' and NEVER 'Workflow Catalogue' (D-11)", async () => {
    render(<SavedWorkflowsPage />);

    const heading = await screen.findByText("My Workflows");
    expect(heading.tagName).toBe("H1");
    // The reserved marketplace wording must be gone.
    expect(screen.queryByText(/Workflow Catalogue/i)).toBeNull();
    expect(screen.queryByText(/Catalogue/i)).toBeNull();
  });
});

describe("SavedWorkflowsPage — grid, empty + search-filtered states (Phase 40 shell)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
  });

  it("renders one card per seeded row (populated grid)", async () => {
    mockGetUserWorkflows.mockResolvedValue([
      { ...ROW, id: "uw-1", name: "Alpha deck", base_pipeline_type: "ppt" },
      { ...ROW, id: "uw-2", name: "Beta migration", base_pipeline_type: "mulesoft_to_springboot" },
    ]);
    render(<SavedWorkflowsPage />);
    expect(await screen.findByText("Alpha deck")).toBeInTheDocument();
    expect(screen.getByText("Beta migration")).toBeInTheDocument();
    // Each card carries its own "Run workflow" launch action.
    expect(screen.getAllByRole("button", { name: /Run workflow/ })).toHaveLength(2);
  });

  it("shows the empty state (no cards) when the list is empty", async () => {
    mockGetUserWorkflows.mockResolvedValue([]);
    render(<SavedWorkflowsPage />);
    expect(await screen.findByText("No workflows saved yet")).toBeInTheDocument();
    // No launch actions and no search toolbar when there are zero workflows.
    expect(screen.queryByRole("button", { name: /Run workflow/ })).toBeNull();
    expect(screen.queryByPlaceholderText(/Search workflows/i)).toBeNull();
  });

  it("filters the grid by the search query and offers a clear-search escape", async () => {
    const user = userEvent.setup();
    mockGetUserWorkflows.mockResolvedValue([
      { ...ROW, id: "uw-1", name: "Alpha deck", description: "", base_pipeline_type: "ppt" },
      { ...ROW, id: "uw-2", name: "Beta migration", description: "", base_pipeline_type: "prototype" },
    ]);
    render(<SavedWorkflowsPage />);
    await screen.findByText("Alpha deck");

    const box = screen.getByPlaceholderText(/Search workflows/i);
    await user.type(box, "Alpha");
    // The non-matching row drops out.
    expect(screen.getByText("Alpha deck")).toBeInTheDocument();
    expect(screen.queryByText("Beta migration")).toBeNull();

    // A query matching nothing yields the "no results" affordance + a clear button.
    await user.clear(box);
    await user.type(box, "zzz-nothing");
    expect(await screen.findByText(/No workflows match/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Clear search/i }));
    expect(await screen.findByText("Alpha deck")).toBeInTheDocument();
    expect(screen.getByText("Beta migration")).toBeInTheDocument();
  });
});

describe("SavedWorkflowsPage — kebab a11y (aria + Escape)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetUserWorkflows.mockResolvedValue(makeRows());
  });

  it("kebab trigger exposes aria-haspopup/expanded and the menu is Escape-closable", async () => {
    const user = userEvent.setup();
    render(<SavedWorkflowsPage />);

    const trigger = await screen.findByRole("button", { name: "Workflow actions" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    // Opening flips aria-expanded and reveals a role=menu with menuitems.
    // NB: the mocked motion proxy remounts the card subtree on each state
    // change, so re-query the (fresh) trigger node after the click. Real
    // motion keeps the same node — this is a test-harness artifact only.
    await user.click(trigger);
    const openTrigger = screen.getByRole("button", { name: "Workflow actions" });
    expect(openTrigger).toHaveAttribute("aria-expanded", "true");
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(4);

    // Escape closes the menu and the trigger reflects the collapsed state (a11y).
    openTrigger.focus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(screen.getByRole("button", { name: "Workflow actions" }))
      .toHaveAttribute("aria-expanded", "false");
  });
});

describe("SavedWorkflowsPage — kebab CRUD is real, not static text (D-15)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockReturnValue("test-token");
    mockGetUserWorkflows.mockResolvedValue(makeRows());
  });

  it("Rename → invokes renameUserWorkflow and optimistically updates the row", async () => {
    const user = userEvent.setup();
    mockRenameUserWorkflow.mockResolvedValue({ ...ROW, name: "Renamed WF" });
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");

    await openKebabAndClick(user, "Rename");

    // The Rename modal preloads the current name; change it and save.
    const nameInput = await screen.findByDisplayValue("My saved workflow");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed WF");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mockRenameUserWorkflow).toHaveBeenCalledTimes(1));
    // Real wiring: (jwt, id, { name, description }).
    expect(mockRenameUserWorkflow.mock.calls[0][1]).toBe("uw-1");
    expect(mockRenameUserWorkflow.mock.calls[0][2]).toMatchObject({ name: "Renamed WF" });
    // Optimistic list mutation — the resolved row replaces the old name.
    expect(await screen.findByText("Renamed WF")).toBeInTheDocument();
    expect(screen.queryByText("My saved workflow")).toBeNull();
  });

  it("Duplicate → invokes createUserWorkflow and prepends the copy", async () => {
    const user = userEvent.setup();
    mockCreateUserWorkflow.mockResolvedValue({
      ...ROW, id: "uw-copy", name: "My saved workflow (copy)",
    });
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");

    await openKebabAndClick(user, "Duplicate");

    await waitFor(() => expect(mockCreateUserWorkflow).toHaveBeenCalledTimes(1));
    // Real wiring: (jwt, { name: "<name> (copy)", base_pipeline_type, agent_ids, ... }).
    expect(mockCreateUserWorkflow.mock.calls[0][1]).toMatchObject({
      name: "My saved workflow (copy)",
      base_pipeline_type: "custom",
      agent_ids: ["a1", "a2"],
    });
    expect(await screen.findByText("My saved workflow (copy)")).toBeInTheDocument();
  });

  it("Delete → confirm invokes deleteUserWorkflow and removes the row", async () => {
    const user = userEvent.setup();
    mockDeleteUserWorkflow.mockResolvedValue(undefined);
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");

    await openKebabAndClick(user, "Delete");

    // The confirm modal (role=dialog) opens; click its primary Delete button.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete workflow")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(mockDeleteUserWorkflow).toHaveBeenCalledTimes(1));
    expect(mockDeleteUserWorkflow.mock.calls[0][1]).toBe("uw-1");
    // Optimistic removal after the server delete resolved.
    await waitFor(() => expect(screen.queryByText("My saved workflow")).toBeNull());
  });

  it("Edit → calls router.push with routes.workflowEdit(id)", async () => {
    const user = userEvent.setup();
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");

    await openKebabAndClick(user, "Edit");

    await waitFor(() => expect(mockRouterPush).toHaveBeenCalledTimes(1));
    expect(mockRouterPush).toHaveBeenCalledWith(routes.workflowEdit("uw-1"));
  });
});
