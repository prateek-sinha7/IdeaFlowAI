/**
 * Phase 35 / 35-07 (B1-07, ND-12) — admin console reskin render contract.
 *
 * The admin page is being reskinned onto the Phase-32 token layer + ui/* primitives
 * (Card/Badge/Button/Pill). This test is the RED->GREEN gate for that reskin AND a
 * regression guard on the product's RICHER wiring that a face-value mock rebuild
 * would drop.
 *
 * Two layers, asserted together:
 *
 *  1. WIRING PRESERVATION (must stay green across the reskin):
 *       - the users table renders the Runs / Role / Joined columns (the product's
 *         richer columns backed by workflow_run_count / is_admin / created_at);
 *       - the create-user modal contains a password field (type="password") — THE
 *         admin password-create flow the phase protects;
 *       - the is_admin access gate remains: a non-admin user is redirected.
 *
 *  2. RESKIN STATE (some RED now, GREEN after the page is reskinned):
 *       - the TierDropdown trigger exposes aria-expanded; the open menu carries
 *         role="menu" and closes on Escape (menu-button a11y pattern);
 *       - NO "Status" or "Last active" column header renders — the defer guard:
 *         AdminUser has no display_name/status/last_active_at, so no unbacked
 *         columns are surfaced (ND-12, INV-3).
 *
 * next/navigation + @/lib/api are stubbed so the client page renders in jsdom
 * without a router context or a live transport (LOCK-B: no network).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { replaceMock, pushMock, api } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  pushMock: vi.fn(),
  api: {
    getToken: vi.fn(() => "tok"),
    getMe: vi.fn(),
    logout: vi.fn(),
    adminListUsers: vi.fn(),
    adminUpdateTier: vi.fn(),
    adminCreateUser: vi.fn(),
    adminDeleteUser: vi.fn(),
  },
}));

// next/navigation — AdminPage calls useRouter() at the top of the body.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock, prefetch: vi.fn() }),
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
    created_at: "2026-01-15T09:00:00Z",
    workflow_run_count: 12,
  },
  {
    id: "bbbb1111-2222-3333-4444-555566667777",
    email: "bob@example.com",
    tier: "basic" as const,
    is_admin: true,
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

  it("create-user modal contains a password field plus email + plan + grant-admin", async () => {
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /add user/i }));

    await screen.findByText(/create new user/i);

    // A password input is the protected admin password-create flow.
    expect(document.querySelector('input[type="password"]')).not.toBeNull();
    // Email input + grant-admin checkbox present too.
    expect(document.querySelector('input[type="email"]')).not.toBeNull();
    expect(document.querySelector('input[type="checkbox"]')).not.toBeNull();
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
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/dashboard"));
    // The user table is never populated for a non-admin.
    expect(screen.queryByText("alice@example.com")).toBeNull();
  });

  it("does NOT render a Status or Last active column (defer guard — no backing fields)", async () => {
    await renderAsAdmin();
    expect(screen.queryByRole("columnheader", { name: /status/i })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /last active/i })).toBeNull();
  });
});

// keep `within` import referenced (row-scoped helper available for future assertions)
void within;
