/**
 * Phase 35 plan-01 (B1-01) — AppHeader a11y + nav-label contract (RED-first).
 *
 * Encodes the SHELL a11y invariant the reskin must satisfy (D-15 keep-behavior,
 * D-11 relabel, SC-001 generic routing). Authored BEFORE the reskin, so these
 * assertions FAIL against the current header (no aria-current, no
 * aria-haspopup/expanded, no role=menu/menuitem, no Escape-refocus, and the
 * third nav item still reads "Catalogue"). The Task-2 reskin turns them GREEN.
 *
 * Mirrors the render-test conventions in ReviewGatesSection.test.tsx
 * (vitest describe/it + @testing-library/react + userEvent).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// next/navigation — AppHeader calls useRouter() to route the admin-only
// "Admin Dashboard" menu item to /admin.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { AppHeader } from "./AppHeader";

type HeaderOverrides = Partial<React.ComponentProps<typeof AppHeader>>;

function setup(overrides: HeaderOverrides = {}) {
  const onNavigate = vi.fn();
  const onLogout = vi.fn();
  render(
    <AppHeader
      currentPage="saved-workflows"
      onNavigate={onNavigate}
      onLogout={onLogout}
      userEmail="qa@flowin.test"
      userTier="basic"
      {...overrides}
    />,
  );
  return { onNavigate, onLogout };
}

describe("AppHeader — nav label (D-11)", () => {
  it("renders the visible 'My Workflows' label and NOT 'Catalogue'", () => {
    setup();
    expect(
      screen.getByRole("button", { name: /my workflows/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/catalogue/i)).not.toBeInTheDocument();
  });

  it("clicking 'My Workflows' routes to the generic page key saved-workflows (SC-001)", async () => {
    const user = userEvent.setup();
    const { onNavigate } = setup();
    await user.click(screen.getByRole("button", { name: /my workflows/i }));
    expect(onNavigate).toHaveBeenCalledWith("saved-workflows");
  });
});

describe("AppHeader — active nav aria-current", () => {
  it("exposes aria-current='page' on the active nav item only", () => {
    setup({ currentPage: "saved-workflows" });
    expect(
      screen.getByRole("button", { name: /my workflows/i }),
    ).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /home/i })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("moves aria-current when a different page is active", () => {
    setup({ currentPage: "home" });
    expect(screen.getByRole("button", { name: /home/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("button", { name: /my workflows/i }),
    ).not.toHaveAttribute("aria-current");
  });
});

describe("AppHeader — Admin Dashboard nav item (gated by isAdmin)", () => {
  it("does NOT render 'Admin Dashboard' for a non-admin user", async () => {
    const user = userEvent.setup();
    setup({ isAdmin: false });
    await user.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.queryByRole("menuitem", { name: /admin dashboard/i })).not.toBeInTheDocument();
  });

  it("renders 'Admin Dashboard' in the profile menu for an admin user", async () => {
    const user = userEvent.setup();
    setup({ isAdmin: true });
    await user.click(screen.getByRole("button", { name: /account menu/i }));
    expect(screen.getByRole("menuitem", { name: /admin dashboard/i })).toBeInTheDocument();
  });
});

describe("AppHeader — profile menu a11y", () => {
  it("profile trigger advertises aria-haspopup=menu and toggles aria-expanded", async () => {
    const user = userEvent.setup();
    setup();
    const trigger = screen.getByRole("button", { name: /account menu/i });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("open dropdown is role=menu with a menuitem per action", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /account menu/i }));
    const menu = screen.getByRole("menu");
    const items = within(menu).getAllByRole("menuitem");
    // Account Settings / Security / Analytics / Workflow History / Log out.
    // Security was added with the MFA enrolment page — without a route into it,
    // ADMIN_MFA_REQUIRED is a lockout switch rather than a control.
    expect(items).toHaveLength(5);
    expect(
      within(menu).getByRole("menuitem", { name: /account settings/i }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("menuitem", { name: /security/i }),
    ).toBeInTheDocument();
    expect(
      within(menu).getByRole("menuitem", { name: /log out/i }),
    ).toBeInTheDocument();
  });

  it("Escape closes the menu and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    setup();
    const trigger = screen.getByRole("button", { name: /account menu/i });
    await user.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("menu")).not.toBeInTheDocument(),
    );
    expect(trigger).toHaveFocus();
  });
});
