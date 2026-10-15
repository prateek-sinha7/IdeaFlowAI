/**
 * QA-KB-109 analysis probe (frontend, offline, jsdom). Application source and the existing
 * admin tests are NOT edited; this file only renders the real AdminPage with the same module
 * mocks the repo's own admin.actions.test.tsx uses, except for two deliberate differences:
 *
 *  1. getMe() returns an `id` that matches one listed row (the signed-in admin's own row).
 *     The repo's T14 tests mock getMe WITHOUT an id and never list the signed-in admin, so
 *     they cannot see this bug (admin.actions.test.tsx:84, admin.reskin.test.tsx:122).
 *  2. The `motion` mock caches one component type per tag. The repo's mock returns a NEW
 *     component type on every property access, which remounts every row on every render and
 *     would reset TierDropdown's local state in a way the real app never does (the file says
 *     so itself, admin.reskin.test.tsx:210-214). A stable type matches real motion/react.
 *
 * Tests named "[today]" assert what the page does NOW (green now, meant to flip with the fix).
 * Tests named "[contract, RED today]" are what the fix must meet. They run under `it.fails`, so
 * they pass only while the defect exists; with PROBE_TARGET=fixed they run as plain `it` against
 * page.reference-fix.tsx (a copy of the page with the smallest change, never applied to the app).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { routerObj, api } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail: unknown) {
      // Same shape as lib/api.ts:277-286: message comes from the server's detail string.
      super(typeof detail === "string" ? detail : JSON.stringify(detail));
      this.status = status;
      this.detail = detail;
    }
  }
  return {
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
      adminResetUserPassword: vi.fn(),
      adminListCapacity: vi.fn(() => new Promise(() => {})),
      onAdminMfaRequired: vi.fn(() => () => {}),
      ApiError,
    },
  };
});

vi.mock("next/navigation", () => ({ useRouter: () => routerObj }));
vi.mock("@/lib/api", () => api);

const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover", "whileTap", "whileFocus",
  "whileInView", "viewport", "layout", "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => {
  const cache = new Map<string, React.ComponentType<Record<string, unknown>>>();
  return {
    motion: new Proxy({}, {
      get: (_t, tag: string) => {
        if (!cache.has(tag)) {
          cache.set(tag, ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
            React.createElement(tag, Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))), children));
        }
        return cache.get(tag);
      },
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

import AdminPage from "@/app/admin/page";

// PROBE_TARGET=fixed (see vitest.probe.config.ts) swaps `@/app/admin/page` for page.reference-fix.tsx:
// the "[today]" tests then skip, and the contract tests run as ordinary tests that must pass.
const FIXED = process.env.PROBE_TARGET === "fixed";
const today = FIXED ? it.skip : it;
const contract = FIXED ? it : it.fails;

const base = { status: "active" as const, created_at: "2026-09-24T09:00:00Z" };
const SELF = { ...base, id: "11111111-aaaa-bbbb-cccc-000000000001", email: "admin@velocity.ai", tier: "enterprise" as const, is_admin: true, workflow_run_count: 64 };
const OTHER_ADMIN = { ...base, id: "22222222-aaaa-bbbb-cccc-000000000002", email: "bob@velocity.ai", tier: "basic" as const, is_admin: true, workflow_run_count: 3 };
const ALICE = { ...base, id: "33333333-aaaa-bbbb-cccc-000000000003", email: "alice@velocity.ai", tier: "pro" as const, is_admin: false, workflow_run_count: 12 };
const ME_REPLY = { id: SELF.id, email: SELF.email, tier: "enterprise", is_admin: true };

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue(ME_REPLY);
  api.adminListUsers.mockResolvedValue([SELF, OTHER_ADMIN, ALICE]);
});

async function renderAsAdmin() {
  render(<AdminPage />);
  await screen.findByText(ALICE.email);
}

const rowOf = (email: string) => screen.getByText(email).closest("tr") as HTMLElement;

function inventory(row: HTMLElement) {
  return within(row)
    .getAllByRole("button")
    .map((b) => ({
      control:
        b.getAttribute("aria-label") ??
        (b.getAttribute("aria-haspopup") === "menu" ? `tier dropdown (${b.textContent?.trim()})` : (b.textContent ?? "").trim()),
      disabled: (b as HTMLButtonElement).disabled,
    }));
}

/** True when a control matching `name` exists in the row and is not disabled. */
const offered = (row: HTMLElement, name: RegExp) => {
  const b = within(row).queryByRole("button", { name });
  return b !== null && !(b as HTMLButtonElement).disabled;
};
const tierTrigger = (row: HTMLElement) => row.querySelector('[aria-haspopup="menu"]') as HTMLButtonElement | null;
const tierOffered = (row: HTMLElement) => { const t = tierTrigger(row); return t !== null && !t.disabled; };

describe("QA-KB-109 probe: the signed-in admin's own row", () => {
  today("[today] P1 inventory: the own row carries the same controls as every other row", async () => {
    await renderAsAdmin();
    for (const u of [SELF, OTHER_ADMIN, ALICE]) {
      const tag = u === SELF ? "OWN ROW  " : u === OTHER_ADMIN ? "OTHER ADMIN" : "PLAIN USER";
      console.log(`[P1] ${tag} ${u.email}: ${JSON.stringify(inventory(rowOf(u.email)))}`);
    }
    const own = rowOf(SELF.email);
    expect(offered(own, /^delete admin@velocity\.ai$/i)).toBe(true);
    expect(offered(own, /^disable admin@velocity\.ai$/i)).toBe(true);
    expect(offered(own, /^reset password for admin@velocity\.ai$/i)).toBe(true);
    expect(offered(own, /^remove admin access from admin@velocity\.ai$/i)).toBe(true);
    expect(tierOffered(own)).toBe(true);
  });

  today("[today] P2 clicking Delete then confirming sends the DELETE for the admin's own id; the modal stays open on the 400", async () => {
    api.adminDeleteUser.mockRejectedValue(new api.ApiError(400, "You cannot delete your own account."));
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf(SELF.email)).getByRole("button", { name: /^delete admin@velocity\.ai$/i }));
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.adminDeleteUser).toHaveBeenCalledWith("tok", SELF.id));
    const toast = await screen.findByText(/failed to delete user/i);
    console.log(`[P2] DELETE sent for own id ${SELF.id}; toast=${JSON.stringify(toast.textContent)}; modal still open=${screen.queryByRole("heading", { name: /delete user\?/i }) !== null}; server's sentence shown anywhere=${screen.queryByText(/cannot delete your own account/i) !== null}`);
    expect(screen.queryByText(/cannot delete your own account/i)).toBeNull();
    expect(screen.queryByRole("heading", { name: /delete user\?/i })).not.toBeNull();
  });

  today("[today] P3 the role pill sends the self-demote (the guard b2a621f84 removed)", async () => {
    api.adminUpdateRole.mockRejectedValue(new api.ApiError(400, "You cannot remove your own admin access."));
    await renderAsAdmin();
    const user = userEvent.setup();
    const pill = within(rowOf(SELF.email)).getByRole("button", { name: /^remove admin access from admin@velocity\.ai$/i });
    console.log(`[P3] own-row role pill: disabled=${(pill as HTMLButtonElement).disabled} title=${JSON.stringify(pill.getAttribute("title"))}`);
    await user.click(pill);
    await waitFor(() => expect(api.adminUpdateRole).toHaveBeenCalledWith("tok", SELF.id, false));
    console.log(`[P3] PATCH role is_admin=false sent for own id; toast=${JSON.stringify((await screen.findByText(/cannot remove your own admin access/i)).textContent)}`);
  });

  today("[today] P4 Disable sends the disable for the admin's own id", async () => {
    api.adminDisableUser.mockRejectedValue(new api.ApiError(400, "You cannot disable your own account."));
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf(SELF.email)).getByRole("button", { name: /^disable admin@velocity\.ai$/i }));
    await waitFor(() => expect(api.adminDisableUser).toHaveBeenCalledWith("tok", SELF.id));
    console.log(`[P4] POST disable sent for own id; toast=${JSON.stringify((await screen.findByText(/cannot disable your own account/i)).textContent)}`);
  });

  today("[today] P5 the tier dropdown keeps showing the refused tier after the server says 400", async () => {
    api.adminUpdateTier.mockRejectedValue(new api.ApiError(400, "You cannot change your own tier. Ask another administrator."));
    await renderAsAdmin();
    const user = userEvent.setup();
    const own = rowOf(SELF.email);
    const trigger = tierTrigger(own)!;
    console.log(`[P5] before: trigger label=${JSON.stringify(trigger.textContent?.trim())} (server tier for this row: ${SELF.tier})`);
    await user.click(trigger);
    await user.click(await screen.findByRole("menuitem", { name: /basic/i }));
    await waitFor(() => expect(api.adminUpdateTier).toHaveBeenCalledWith("tok", SELF.id, "basic"));
    const toast = await screen.findByText(/cannot change your own tier/i);
    await waitFor(() => expect(trigger.querySelector(".animate-spin")).toBeNull());
    const after = tierTrigger(rowOf(SELF.email))!.textContent?.trim();
    console.log(`[P5] after the 400 toast ${JSON.stringify(toast.textContent)}: trigger label=${JSON.stringify(after)} (the mocked PATCH was rejected, so the server still holds ${SELF.tier})`);
    expect(after).toMatch(/basic/i);
  });

  today("[today] P5b the stale badge is cleared only when the row remounts: the refresh button does it (loading state replaces the table)", async () => {
    api.adminUpdateTier.mockRejectedValue(new api.ApiError(400, "You cannot change your own tier. Ask another administrator."));
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger(rowOf(SELF.email))!);
    await user.click(await screen.findByRole("menuitem", { name: /basic/i }));
    await screen.findByText(/cannot change your own tier/i);
    await waitFor(() => expect(tierTrigger(rowOf(SELF.email))!.querySelector(".animate-spin")).toBeNull());
    const stale = tierTrigger(rowOf(SELF.email))!.textContent?.trim();
    const refresh = document.querySelector("button svg.lucide-refresh-cw")?.closest("button") as HTMLButtonElement;
    await user.click(refresh);
    await screen.findByText(ALICE.email);
    const after = tierTrigger(rowOf(SELF.email))!.textContent?.trim();
    console.log(`[P5b] stale label=${JSON.stringify(stale)}; after the refresh button (adminListUsers calls: ${api.adminListUsers.mock.calls.length}) label=${JSON.stringify(after)}`);
    expect(stale).toMatch(/basic/i);
    expect(after).toMatch(/enterprise/i);
  });

  today("[today] P6 Reset password sends the reset for the admin's own id and the page reports success", async () => {
    api.adminResetUserPassword.mockResolvedValue({ status: "temporary_password_set" });
    await renderAsAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf(SELF.email)).getByRole("button", { name: /^reset password for admin@velocity\.ai$/i }));
    await waitFor(() => expect(api.adminResetUserPassword).toHaveBeenCalledWith("tok", SELF.id));
    console.log(`[P6] POST reset-password sent for own id; toast=${JSON.stringify((await screen.findByText(/temporary password issued/i)).textContent)}`);
  });

  it("[control, must stay green after the fix] P7 another admin's row and a plain row keep every control (the repo's T14 contract)", async () => {
    await renderAsAdmin();
    const bob = rowOf(OTHER_ADMIN.email);
    expect(offered(bob, /^delete bob@velocity\.ai$/i)).toBe(true);
    expect(offered(bob, /^disable bob@velocity\.ai$/i)).toBe(true);
    expect(offered(bob, /^reset password for bob@velocity\.ai$/i)).toBe(true);
    expect(offered(bob, /^remove admin access from bob@velocity\.ai$/i)).toBe(true);
    expect(tierOffered(bob)).toBe(true);
    const alice = rowOf(ALICE.email);
    expect(offered(alice, /^delete alice@velocity\.ai$/i)).toBe(true);
    expect(offered(alice, /^grant admin access to alice@velocity\.ai$/i)).toBe(true);
  });

  it("[control, must stay green after the fix] P8 with getMe() carrying no id (as in the repo's T14 tests) no row is treated as the user's own", async () => {
    api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
    await renderAsAdmin();
    for (const u of [SELF, OTHER_ADMIN, ALICE]) {
      expect(offered(rowOf(u.email), new RegExp(`^delete ${u.email.replace(".", "\\.")}$`, "i"))).toBe(true);
    }
  });

  // ---- the contract, RED today ------------------------------------------------------------

  contract("[contract, RED today] C1 the own row has NO Delete control (S-11-04); other rows keep theirs", async () => {
    await renderAsAdmin();
    expect(within(rowOf(SELF.email)).queryByRole("button", { name: /^delete admin@velocity\.ai$/i })).toBeNull();
    expect(within(rowOf(OTHER_ADMIN.email)).queryByRole("button", { name: /^delete bob@velocity\.ai$/i })).not.toBeNull();
    expect(within(rowOf(ALICE.email)).queryByRole("button", { name: /^delete alice@velocity\.ai$/i })).not.toBeNull();
  });

  contract("[contract, RED today] C2 the own row offers no live Disable, role-demote, tier or Reset-password control", async () => {
    await renderAsAdmin();
    const own = rowOf(SELF.email);
    expect(offered(own, /^disable admin@velocity\.ai$/i)).toBe(false);
    expect(offered(own, /^remove admin access from admin@velocity\.ai$/i)).toBe(false);
    expect(tierOffered(own)).toBe(false);
    expect(offered(own, /^reset password for admin@velocity\.ai$/i)).toBe(false);
  });
});
