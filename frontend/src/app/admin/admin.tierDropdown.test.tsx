/**
 * AdminPage — TierDropdown (module-private, exercised through the page).
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

const ALICE: AdminUser = {
  id: "user-1",
  email: "alice@example.com",
  tier: "pro",
  is_admin: false,
  status: "active",
  created_at: "2026-01-15T12:00:00Z",
  workflow_run_count: 12,
};
const BOB: AdminUser = { ...ALICE, id: "user-2", email: "bob@example.com", tier: "basic" };

function rowOf(email: string): HTMLElement {
  return screen.getByText(email).closest("tr") as HTMLElement;
}

/** The tier trigger is the only button in a row that has aria-haspopup="menu". */
function tierTrigger(email: string): HTMLElement {
  const trigger = rowOf(email).querySelector('[aria-haspopup="menu"]');
  if (!trigger) throw new Error(`no tier trigger for ${email}`);
  return trigger as HTMLElement;
}

function statValue(label: string): string {
  return screen.getByText(label, { selector: "p" }).nextElementSibling?.textContent ?? "";
}

async function renderAdmin(users: AdminUser[] = [ALICE, BOB]) {
  api.adminListUsers.mockResolvedValue(users);
  render(<AdminPage />);
  await screen.findByText(users[0].email);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

describe("AdminPage — tier dropdown", () => {
  it("lists the four tiers in order when opened", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));

    const menu = await screen.findByRole("menu");
    const labels = within(menu).getAllByRole("menuitem").map((item) => item.textContent);
    expect(labels).toEqual(["Basic", "Pro", "Enterprise", "Hexaware"]);
    expect(tierTrigger("alice@example.com")).toHaveAttribute("aria-expanded", "true");
  });

  it("closes without calling the API when the current tier is selected", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Pro" }));

    expect(screen.queryByRole("menu")).toBeNull();
    expect(api.adminUpdateTier).not.toHaveBeenCalled();
  });

  it("updates the tier, stats, trigger label and shows a success toast when a new tier is chosen", async () => {
    api.adminUpdateTier.mockResolvedValue({ ...ALICE, tier: "enterprise" });
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Enterprise" }));

    expect(await screen.findByText("Tier updated to Enterprise")).toBeInTheDocument();
    expect(api.adminUpdateTier).toHaveBeenCalledWith("tok", "user-1", "enterprise");
    expect(tierTrigger("alice@example.com")).toHaveTextContent("Enterprise");
    expect(statValue("Pro")).toBe("0");
    expect(statValue("Enterprise")).toBe("1");
  });

  it("disables the trigger while the update is pending and re-enables it afterwards", async () => {
    let resolveUpdate: (value: AdminUser) => void = () => {};
    api.adminUpdateTier.mockReturnValue(new Promise((resolve) => { resolveUpdate = resolve; }));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Basic" }));

    expect(tierTrigger("alice@example.com")).toBeDisabled();

    await act(async () => { resolveUpdate({ ...ALICE, tier: "basic" }); });
    await waitFor(() => expect(tierTrigger("alice@example.com")).toBeEnabled());
  });

  it("shows the error message in a toast when the tier update is rejected", async () => {
    api.adminUpdateTier.mockRejectedValue(new Error("Tier change denied"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Basic" }));

    expect(await screen.findByText("Tier change denied")).toBeInTheDocument();
  });

  it("falls back to a generic toast when the tier update rejects with a non-Error", async () => {
    api.adminUpdateTier.mockRejectedValue("nope");
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Basic" }));

    expect(await screen.findByText("Failed to update tier")).toBeInTheDocument();
  });

  // LIKELY DEFECT (reported, not fixed): AdminPage.handleUpdateTier catches its own
  // error and never rethrows, so TierDropdown's `catch { setLocalTier(currentTier) }`
  // revert is unreachable and the trigger keeps showing the failed (optimistic)
  // tier while the server still holds the old one. This test states the intended
  // contract; `it.fails` keeps the evidence visible and flips red once production
  // is fixed (then remove `.fails`).
  it.fails("reverts the trigger to the original tier when the update is rejected", async () => {
    api.adminUpdateTier.mockRejectedValue(new Error("Tier change denied"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("bob@example.com"));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Pro" }));

    await screen.findByText("Tier change denied");
    await waitFor(() => expect(tierTrigger("bob@example.com")).toBeEnabled());
    expect(tierTrigger("bob@example.com")).toHaveTextContent("Basic");
  });

  it("does not call the API when the token has gone missing at action time", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    const menu = await screen.findByRole("menu");
    api.getToken.mockReturnValue(null);
    await user.click(within(menu).getByRole("menuitem", { name: "Basic" }));

    await waitFor(() => expect(tierTrigger("alice@example.com")).toBeEnabled());
    expect(api.adminUpdateTier).not.toHaveBeenCalled();
  });

  it("closes the menu when the backdrop is clicked", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(tierTrigger("alice@example.com"));
    const menu = await screen.findByRole("menu");

    // The backdrop is a plain <div> with no role/label; it is the menu's previous sibling.
    const backdrop = menu.previousElementSibling as HTMLElement;
    await user.click(backdrop);

    expect(screen.queryByRole("menu")).toBeNull();
    expect(tierTrigger("alice@example.com")).toHaveAttribute("aria-expanded", "false");
  });

  it("shows the raw tier string for a tier missing from the label table", async () => {
    const legacy = { ...ALICE, tier: "legacy" as unknown as AdminUser["tier"] };
    await renderAdmin([legacy]);
    expect(tierTrigger("alice@example.com")).toHaveTextContent("legacy");
  });

  it("shows the refreshed tier after the list is reloaded", async () => {
    await renderAdmin([ALICE]);
    const user = userEvent.setup();
    api.adminListUsers.mockResolvedValue([{ ...ALICE, tier: "hexaware" }]);

    const search = screen.getByRole("textbox", { name: "Search users" });
    const refresh = within(search.parentElement?.parentElement as HTMLElement).getAllByRole("button")[0];
    await user.click(refresh);

    await waitFor(() => expect(tierTrigger("alice@example.com")).toHaveTextContent("Hexaware"));
  });
});
