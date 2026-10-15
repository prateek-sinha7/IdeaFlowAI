// ISS-1153 (QA-KB-109): the signed-in admin's own row must not offer Delete; ISS-1168: nor a live
// Disable, role-demote, tier or Reset-password control. Other rows keep every control (T14 contract).
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
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

import AdminPage from "./page";


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

function _inventory(row: HTMLElement) {
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


describe("QA-KB-109: the signed-in admin's own row", () => {
  it("ISS-1153: the own row has NO Delete control; other rows keep theirs", async () => {
    await renderAsAdmin();
    expect(within(rowOf(SELF.email)).queryByRole("button", { name: /^delete admin@velocity\.ai$/i })).toBeNull();
    expect(within(rowOf(OTHER_ADMIN.email)).queryByRole("button", { name: /^delete bob@velocity\.ai$/i })).not.toBeNull();
    expect(within(rowOf(ALICE.email)).queryByRole("button", { name: /^delete alice@velocity\.ai$/i })).not.toBeNull();
  });

  it("ISS-1168: the own row offers no live Disable, role-demote, tier or Reset-password control", async () => {
    await renderAsAdmin();
    const own = rowOf(SELF.email);
    expect(offered(own, /^disable admin@velocity\.ai$/i)).toBe(false);
    expect(offered(own, /^remove admin access from admin@velocity\.ai$/i)).toBe(false);
    expect(tierOffered(own)).toBe(false);
    expect(offered(own, /^reset password for admin@velocity\.ai$/i)).toBe(false);
  });
});
