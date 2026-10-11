/**
 * AdminPage — users table: stats, search, avatar, id/date/run rendering,
 * disabled status, refresh, default tab.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { AdminUser } from "@/lib/api";

const { routerObj, api } = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail: unknown, message = "") {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  }
  return {
    routerObj: { replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() },
    api: {
      ApiError,
      getToken: vi.fn((): string | null => "tok"),
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
      adminListCapacity: vi.fn(),
      onAdminMfaRequired: vi.fn((cb: (detail: { enroll_path: string }) => void): (() => void) => { void cb; return () => {}; }),
    },
  };
});

vi.mock("next/navigation", () => ({ useRouter: () => routerObj }));
vi.mock("@/lib/api", () => api);

// Stable component identity per tag (unlike a naive Proxy) so rows do not remount.
vi.mock("motion/react", () => {
  const STRIPPED = new Set([
    "initial", "animate", "exit", "transition", "whileHover", "whileTap",
    "whileFocus", "whileInView", "viewport", "layout", "layoutId", "drag",
    "dragConstraints", "variants", "custom",
  ]);
  const cache = new Map<string, React.ComponentType<Record<string, unknown>>>();
  return {
    motion: new Proxy({}, {
      get: (_t, tag: string) => {
        if (!cache.has(tag)) {
          cache.set(tag, ({ children, ...rest }: Record<string, unknown>) =>
            React.createElement(
              tag,
              Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))),
              children as React.ReactNode,
            ));
        }
        return cache.get(tag);
      },
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

import AdminPage from "./page";

function makeUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "aaaa1111-2222-3333-4444-555566667777",
    email: "alice@example.com",
    tier: "pro",
    is_admin: false,
    status: "active",
    created_at: "2026-01-15T12:00:00Z",
    workflow_run_count: 12,
    ...overrides,
  };
}

const FIVE_USERS: AdminUser[] = [
  makeUser({ id: "id-basic-1", email: "basic1@example.com", tier: "basic" }),
  makeUser({ id: "id-pro-0001", email: "pro1@example.com", tier: "pro", is_admin: true }),
  makeUser({ id: "id-ent-0001", email: "ent1@example.com", tier: "enterprise" }),
  makeUser({ id: "id-hex-0001", email: "hex1@example.com", tier: "hexaware", is_admin: true }),
  makeUser({ id: "id-pro-0002", email: "pro2@example.com", tier: "pro" }),
];

/** Stat card value rendered under a given label (labels are <p> in the card). */
function statValue(label: string): string {
  const labelEl = screen.getByText(label, { selector: "p" });
  return labelEl.nextElementSibling?.textContent ?? "";
}

/** Count pill next to the "Users" card title. */
function countPill(): string {
  return screen.getByText("Users", { selector: "span" }).nextElementSibling?.textContent ?? "";
}

async function renderAdmin(users: AdminUser[]) {
  api.adminListUsers.mockResolvedValue(users);
  render(<AdminPage />);
  await screen.findByText("Total Users");
  await waitFor(() => expect(screen.queryByText("Loading users...")).toBeNull());
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

describe("AdminPage — users table", () => {
  it("shows the empty state and zeroed stats when there are no users", async () => {
    await renderAdmin([]);
    expect(screen.getByText("No users found")).toBeInTheDocument();
    for (const label of ["Total Users", "Basic", "Pro", "Enterprise", "Hexaware", "Admins"]) {
      expect(statValue(label)).toBe("0");
    }
    expect(countPill()).toBe("0");
  });

  it("counts users per tier and admins in the stat cards", async () => {
    await renderAdmin(FIVE_USERS);
    expect(statValue("Total Users")).toBe("5");
    expect(statValue("Basic")).toBe("1");
    expect(statValue("Pro")).toBe("2");
    expect(statValue("Enterprise")).toBe("1");
    expect(statValue("Hexaware")).toBe("1");
    expect(statValue("Admins")).toBe("2");
    expect(countPill()).toBe("5");
  });

  it("filters rows case-insensitively by email and updates the count pill", async () => {
    await renderAdmin(FIVE_USERS);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Search users" }), "PRO");

    expect(screen.getByText("pro1@example.com")).toBeInTheDocument();
    expect(screen.getByText("pro2@example.com")).toBeInTheDocument();
    expect(screen.queryByText("basic1@example.com")).toBeNull();
    expect(countPill()).toBe("2");
  });

  it("shows the empty state when the search matches nothing and restores rows when cleared", async () => {
    await renderAdmin(FIVE_USERS);
    const user = userEvent.setup();
    const search = screen.getByRole("textbox", { name: "Search users" });

    await user.type(search, "zzz-nobody");
    expect(screen.getByText("No users found")).toBeInTheDocument();

    await user.clear(search);
    expect(screen.getByText("basic1@example.com")).toBeInTheDocument();
    expect(countPill()).toBe("5");
  });

  it("renders the uppercase email initial as the avatar", async () => {
    await renderAdmin([makeUser({ email: "zed@example.com" })]);
    const row = screen.getByText("zed@example.com").closest("tr") as HTMLElement;
    expect(within(row).getByText("Z")).toBeInTheDocument();
  });

  it("renders a '?' avatar instead of crashing when the email is an empty string", async () => {
    await renderAdmin([makeUser({ id: "cccc3333-0000-0000-0000-000000000000", email: "" })]);
    const row = screen.getByText("cccc3333…").closest("tr") as HTMLElement;
    expect(within(row).getByText("?")).toBeInTheDocument();
  });

  it("shows the first 8 characters of the id followed by an ellipsis", async () => {
    await renderAdmin([makeUser()]);
    expect(screen.getByText("aaaa1111…")).toBeInTheDocument();
  });

  it("shows the run count and the formatted join date", async () => {
    await renderAdmin([makeUser({ workflow_run_count: 37, created_at: "2026-01-15T12:00:00Z" })]);
    const row = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
    expect(within(row).getByText("37")).toBeInTheDocument();
    expect(within(row).getByText("Jan 15, 2026")).toBeInTheDocument();
  });

  it("labels a disabled account with a Disabled pill and an enable action", async () => {
    await renderAdmin([makeUser({ status: "disabled" })]);
    const row = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
    expect(within(row).getByText("Disabled")).toBeInTheDocument();
    expect(within(row).queryByText("Active")).toBeNull();
    expect(within(row).getByRole("button", { name: "Enable alice@example.com" })).toBeInTheDocument();
  });

  it("marks the Users tab selected by default", async () => {
    await renderAdmin([makeUser()]);
    expect(screen.getByRole("tab", { name: "Users" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Machines" })).toHaveAttribute("aria-selected", "false");
  });

  // The Refresh button is icon-only with no accessible name (a11y finding, see
  // evidence). It is located structurally: first button in the search toolbar.
  function refreshButton(): HTMLElement {
    const search = screen.getByRole("textbox", { name: "Search users" });
    const toolbar = search.parentElement?.parentElement as HTMLElement;
    return within(toolbar).getAllByRole("button")[0];
  }

  it("reloads users with the stored token when Refresh is clicked", async () => {
    await renderAdmin([makeUser()]);
    expect(api.adminListUsers).toHaveBeenCalledTimes(1);
    const user = userEvent.setup();

    await user.click(refreshButton());

    await waitFor(() => expect(api.adminListUsers).toHaveBeenCalledTimes(2));
    expect(api.adminListUsers).toHaveBeenLastCalledWith("tok");
  });

  it("does not reload users on Refresh when the token has gone missing", async () => {
    await renderAdmin([makeUser()]);
    const user = userEvent.setup();
    api.getToken.mockReturnValue(null);

    await user.click(refreshButton());

    expect(api.adminListUsers).toHaveBeenCalledTimes(1);
  });
});
