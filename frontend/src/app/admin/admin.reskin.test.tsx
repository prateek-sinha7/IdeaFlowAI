/**
 * Phase 35 / 35-07 (B1-07, ND-12) — admin console reskin render contract.
 *
 * The admin page is being reskinned onto the Phase-32 token layer + ui/* primitives
 * (Card/Badge/Button/Pill). This test is the RED->GREEN gate for that reskin AND a
 * regression guard on the product's RICHER wiring that a face-value mock rebuild
 * would drop.
 *
 * Cognito migration (Phase 5, `.kiro/specs/login/prompt.md`) update: user
 * creation is now invitation-only (backend `CreateUserRequest` is
 * `extra=forbid` and has no password field — Decision 6) and the backend's
 * `AdminUserResponse` now carries a `status` field the admin panel can act
 * on. This flips two of this file's own prior assertions:
 *
 *  - the create-user modal used to protect a `type="password"` input; it now
 *    protects the ABSENCE of one plus an invitation notice.
 *  - the "no Status column" defer guard (ND-12: no backing field existed) is
 *    now the opposite assertion — Status IS backed (`AdminUser.status`) and
 *    IS rendered, with a disable/enable action next to it.
 *
 * Two layers, asserted together:
 *
 *  1. WIRING PRESERVATION (must stay green across the reskin):
 *       - the users table renders the Runs / Role / Joined columns (the product's
 *         richer columns backed by workflow_run_count / is_admin / created_at);
 *       - the is_admin access gate remains: a non-admin user is redirected.
 *
 *  2. RESKIN STATE (some RED now, GREEN after the page is reskinned):
 *       - the TierDropdown trigger exposes aria-expanded; the open menu carries
 *         role="menu" and closes on Escape (menu-button a11y pattern);
 *       - a "Status" column IS rendered, backed by `AdminUser.status`.
 *
 * next/navigation + @/lib/api are stubbed so the client page renders in jsdom
 * without a router context or a live transport (LOCK-B: no network).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { routerObj, api } = vi.hoisted(() => ({
  // A stable object, matching real Next.js (useRouter() returns the SAME
  // reference across renders). AdminPage's boot effect depends on `[router,
  // loadUsers]`; a mock that minted a new object on every call would refire
  // that effect on every re-render (including one caused by an admin action
  // like disable/tier-change) and reload+overwrite whatever the action just
  // set — a mock-fragility trap, not a real bug, but one worth avoiding here.
  routerObj: { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() },
  api: {
    getToken: vi.fn(() => "tok"),
    getMe: vi.fn(),
    logout: vi.fn(),
    adminListUsers: vi.fn(),
    adminUpdateTier: vi.fn(),
    adminCreateUser: vi.fn(),
    adminDeleteUser: vi.fn(),
    adminUpdateRole: vi.fn(),
    adminDisableUser: vi.fn(),
    adminEnableUser: vi.fn(),
    // Must return an unsubscribe function — the page registers this as a
    // useEffect cleanup, so returning undefined throws on unmount.
    onAdminMfaRequired: vi.fn(() => () => {}),
  },
}));

// next/navigation — AdminPage calls useRouter() at the top of the body.
vi.mock("next/navigation", () => ({
  useRouter: () => routerObj,
}));

// @/lib/api — never hit the transport from a render test (LOCK-B).
vi.mock("@/lib/api", () => api);

// motion/react — strip animation-only props so motion.* render as plain nodes.
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

import AdminPage from "./page";

const USERS = [
  {
    id: "aaaa1111-2222-3333-4444-555566667777",
    email: "alice@example.com",
    tier: "pro" as const,
    is_admin: false,
    status: "active" as const,
    created_at: "2026-01-15T09:00:00Z",
    workflow_run_count: 12,
  },
  {
    id: "bbbb1111-2222-3333-4444-555566667777",
    email: "bob@example.com",
    tier: "basic" as const,
    is_admin: true,
    status: "active" as const,
    created_at: "2026-02-20T09:00:00Z",
    workflow_run_count: 3,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue(USERS);
});

/** Render as an admin and wait for the users table to load. */
async function renderAsAdmin() {
  render(<AdminPage />);
  // Table loads after getMe() resolves is_admin -> adminListUsers().
  await screen.findByText("alice@example.com");
}

describe("AdminPage reskin — richer-wiring preservation + gate + defer contract", () => {
  it("renders the Runs / Role / Joined columns (richer columns preserved)", async () => {
    await renderAsAdmin();
    expect(screen.getByRole("columnheader", { name: /^runs$/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /^role$/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /^joined$/i })).toBeInTheDocument();
  });

  it("create-user modal is invitation-only: no password field, plus email + plan + grant-admin + invite notice", async () => {
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /add user/i }));

    await screen.findByText(/create new user/i);

    // Cognito migration Phase 5: the backend's CreateUserRequest is
    // extra=forbid and has no password field at all (Decision 6) — a
    // password input here would 422 on submit. Its absence is the
    // protected contract now, not its presence.
    expect(document.querySelector('input[type="password"]')).toBeNull();
    // Email input + grant-admin checkbox present too.
    expect(document.querySelector('input[type="email"]')).not.toBeNull();
    expect(document.querySelector('input[type="checkbox"]')).not.toBeNull();
    // The invitation notice replaces the password field's explanatory role.
    expect(screen.getByText(/temporary password by email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send invitation/i })).toBeInTheDocument();
  });

  it("TierDropdown trigger exposes aria-expanded; open menu has role=menu and closes on Escape", async () => {
    await renderAsAdmin();
    const user = userEvent.setup();

    const trigger = document.querySelector('[aria-haspopup="menu"]') as HTMLElement;
    expect(trigger).not.toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const menu = await screen.findByRole("menu");
    expect(menu).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("redirects a non-admin user (is_admin gate preserved)", async () => {
    api.getMe.mockResolvedValue({ is_admin: false, email: "user@example.com" });
    render(<AdminPage />);
    await waitFor(() => expect(routerObj.replace).toHaveBeenCalledWith("/dashboard"));
    // The user table is never populated for a non-admin.
    expect(screen.queryByText("alice@example.com")).toBeNull();
  });

  it("renders a Status column, backed by AdminUser.status (Phase 5) — 'Last active' still has no backing field", async () => {
    await renderAsAdmin();
    expect(screen.getByRole("columnheader", { name: /^status$/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /last active/i })).toBeNull();
  });

  it("shows an Active pill for an active user and a disable button, not an enable one", async () => {
    await renderAsAdmin();
    const row = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
    expect(within(row).getByText(/^active$/i)).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /disable alice@example\.com/i })).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /enable alice@example\.com/i })).toBeNull();
  });

  it("disabling a user flips its row to the Disabled pill and shows an enable button", async () => {
    api.adminDisableUser.mockResolvedValue({ ...USERS[0], status: "disabled" });
    await renderAsAdmin();
    const user = userEvent.setup();

    const row = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: /disable alice@example\.com/i }));

    await waitFor(() => expect(api.adminDisableUser).toHaveBeenCalled());

    // Re-query fresh rather than holding the `row` reference across the
    // re-render: the mocked motion.tr (a Proxy `get` trap) returns a new
    // closure identity on every access, so React treats each render's
    // motion.tr as a different component type and remounts the subtree —
    // the pre-click `row` node is detached from the document afterward.
    await waitFor(() => {
      const freshRow = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
      expect(within(freshRow).getByText(/^disabled$/i)).toBeInTheDocument();
    });
    const freshRow = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
    expect(within(freshRow).getByRole("button", { name: /enable alice@example\.com/i })).toBeInTheDocument();
    expect(within(freshRow).queryByRole("button", { name: /disable alice@example\.com/i })).toBeNull();
  });

  it("shows disable/delete/demote buttons for admin rows (relying on server 409 for last-admin)", async () => {
    await renderAsAdmin();
    const row = screen.getByText("bob@example.com").closest("tr") as HTMLElement;
    // T14: Removed client-side hiding; now showing all buttons for all users and relying on server to enforce
    expect(within(row).getByRole("button", { name: /disable bob@example\.com/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /delete bob@example\.com/i })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /remove admin access/i })).toBeInTheDocument();
  });
});
