// BUG-104 / ISS-932 (QA-KB-041): Escape must close the Workflow actions menu and the
// Delete confirmation even when focus is on BODY. Correct-behaviour assertions in it.fails:
// red today by design; vitest reports them as failures once the fix lands (remove .fails).
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { mockGetUserWorkflows } = vi.hoisted(() => ({ mockGetUserWorkflows: vi.fn() }));

vi.mock("@/lib/api", () => ({
  getToken: () => "tok",
  getUserWorkflows: (t: string) => mockGetUserWorkflows(t),
  createUserWorkflow: vi.fn(),
  renameUserWorkflow: vi.fn(),
  deleteUserWorkflow: vi.fn(),
}));

// STABLE-identity motion mock: one component type per tag, so nodes survive
// re-renders exactly like real motion (the repo's own mock mints a new type per
// access and remounts the subtree, which silently drops focus).
const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover", "whileTap",
  "whileFocus", "whileInView", "viewport", "layout", "layoutId", "drag",
  "dragConstraints", "variants", "custom",
]);
const cache: Record<string, React.FC<Record<string, unknown>>> = {};
vi.mock("motion/react", () => ({
  motion: new Proxy({}, {
    get: (_t, prop: string) =>
      (cache[prop] ??= ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
        React.createElement(
          prop,
          Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
          children,
        )),
  }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn(() => null) }),
}));

import { SavedWorkflowsPage } from "@/components/savedworkflows/SavedWorkflowsPage";

const ROW = {
  id: "uw-1", name: "My saved workflow", description: "A custom composition.",
  base_pipeline_type: "custom", agent_ids: ["a1", "a2"], model_overrides: null,
  updated_at: "2026-07-01T10:00:00",
};
const trigger = () => screen.getByRole("button", { name: "Workflow actions" });

beforeEach(() => {
  vi.clearAllMocks();
  mockGetUserWorkflows.mockResolvedValue([{ ...ROW }]);
});

describe("BUG-104 — KebabMenu Escape (stable-identity motion mock)", () => {
  it("BUG-104: Escape closes the menu when the opening click did not focus the trigger", async () => {
    const user = userEvent.setup();
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");
    fireEvent.click(trigger()); // no focus move == Safari/Firefox macOS, JS .click()
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}"); // keydown targets BODY
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("BUG-104: Escape dispatched on document.body closes the menu", async () => {
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");
    fireEvent.click(trigger());
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("ISS-932 — Delete-confirm Escape", () => {
  it("ISS-932: Escape closes the Delete workflow confirmation after ordinary clicks", async () => {
    const user = userEvent.setup();
    render(<SavedWorkflowsPage />);
    await screen.findByText("My saved workflow");
    await user.click(trigger());
    const menu = await screen.findByRole("menu");
    await user.click(within(menu).getByText("Delete"));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
