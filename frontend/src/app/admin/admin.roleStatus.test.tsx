/**
 * AdminPage — role toggle, disable/enable, reset password, logout, back-to-app.
 * Happy paths already covered in admin.actions/admin.reskin are not repeated.
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
const BOB: AdminUser = { ...ALICE, id: "user-2", email: "bob@example.com", tier: "basic", is_admin: true };
const DISABLED_CAROL: AdminUser = {
  ...ALICE, id: "user-3", email: "carol@example.com", status: "disabled",
};

function rowOf(email: string): HTMLElement {
  return screen.getByText(email).closest("tr") as HTMLElement;
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

describe("AdminPage — role toggle", () => {
  it("grants admin access: shows the Admin pill, bumps the Admins stat and toasts", async () => {
    api.adminUpdateRole.mockResolvedValue({ ...ALICE, is_admin: true });
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: "Grant admin access to alice@example.com" }));

    expect(await screen.findByText("Admin access granted")).toBeInTheDocument();
    expect(api.adminUpdateRole).toHaveBeenCalledWith("tok", "user-1", true);
    expect(within(rowOf("alice@example.com")).getByText("Admin")).toBeInTheDocument();
    expect(statValue("Admins")).toBe("2");
  });

  it("removes admin access: drops the Admin pill, lowers the Admins stat and toasts", async () => {
    api.adminUpdateRole.mockResolvedValue({ ...BOB, is_admin: false });
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("bob@example.com")).getByRole("button", { name: "Remove admin access from bob@example.com" }));

    expect(await screen.findByText("Admin access removed")).toBeInTheDocument();
    expect(api.adminUpdateRole).toHaveBeenCalledWith("tok", "user-2", false);
    expect(statValue("Admins")).toBe("0");
  });

  it("shows the error message when the role update fails with an Error", async () => {
    api.adminUpdateRole.mockRejectedValue(new Error("nope"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: /grant admin access/i }));
    expect(await screen.findByText("nope")).toBeInTheDocument();
  });

  it("shows a generic message when the role update rejects with a non-Error", async () => {
    api.adminUpdateRole.mockRejectedValue("nope");
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: /grant admin access/i }));
    expect(await screen.findByText("Failed to update role")).toBeInTheDocument();
  });

  it.each([
    ["an object detail with another code", { code: "other" }],
    ["a string detail", "conflict"],
  ])("falls through to the error message on a 409 with %s", async (_label, detail) => {
    api.adminUpdateRole.mockRejectedValue(new api.ApiError(409, detail, "Conflict happened"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("bob@example.com")).getByRole("button", { name: /remove admin access/i }));

    expect(await screen.findByText("Conflict happened")).toBeInTheDocument();
    expect(screen.queryByText("Cannot remove the last administrator.")).toBeNull();
  });

  it("disables only the pending user's role button and re-enables it after a failure", async () => {
    let rejectUpdate: (reason: Error) => void = () => {};
    api.adminUpdateRole.mockReturnValue(new Promise((_resolve, reject) => { rejectUpdate = reject; }));
    await renderAdmin();
    const user = userEvent.setup();
    const aliceButton = within(rowOf("alice@example.com")).getByRole("button", { name: /grant admin access/i });
    await user.click(aliceButton);

    expect(aliceButton).toBeDisabled();
    expect(within(rowOf("bob@example.com")).getByRole("button", { name: /remove admin access/i })).toBeEnabled();

    await act(async () => { rejectUpdate(new Error("late failure")); });
    await screen.findByText("late failure");
    expect(aliceButton).toBeEnabled();
  });

  it("does not call the API when the token has gone missing", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    api.getToken.mockReturnValue(null);
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: /grant admin access/i }));
    expect(api.adminUpdateRole).not.toHaveBeenCalled();
  });
});

describe("AdminPage — disable / enable / reset password", () => {
  it("re-enables a disabled account: Active pill, disable button and toast", async () => {
    api.adminEnableUser.mockResolvedValue({ ...DISABLED_CAROL, status: "active" });
    await renderAdmin([DISABLED_CAROL]);
    const user = userEvent.setup();
    await user.click(within(rowOf("carol@example.com")).getByRole("button", { name: "Enable carol@example.com" }));

    expect(await screen.findByText("User re-enabled")).toBeInTheDocument();
    expect(api.adminEnableUser).toHaveBeenCalledWith("tok", "user-3");
    const row = rowOf("carol@example.com");
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Disable carol@example.com" })).toBeInTheDocument();
  });

  it("shows the thrown message when disabling fails", async () => {
    api.adminDisableUser.mockRejectedValue(new Error("Cannot disable"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: "Disable alice@example.com" }));
    expect(await screen.findByText("Cannot disable")).toBeInTheDocument();
    expect(within(rowOf("alice@example.com")).getByText("Active")).toBeInTheDocument();
  });

  it.each([
    ["disable", "Disable alice@example.com", () => api.adminDisableUser, "Failed to disable user", [ALICE]],
    ["enable", "Enable carol@example.com", () => api.adminEnableUser, "Failed to enable user", [DISABLED_CAROL]],
    ["reset password", "Reset password for alice@example.com", () => api.adminResetUserPassword, "Failed to reset password", [ALICE]],
  ] as const)("shows a generic message when %s rejects with a non-Error", async (_label, buttonName, getFn, message, users) => {
    getFn().mockRejectedValue("nope");
    await renderAdmin([...users]);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: buttonName }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("shows the thrown message when resetting a password fails", async () => {
    api.adminResetUserPassword.mockRejectedValue(new Error("Reset not allowed"));
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(within(rowOf("alice@example.com")).getByRole("button", { name: /reset password/i }));
    expect(await screen.findByText("Reset not allowed")).toBeInTheDocument();
  });

  it.each([
    ["disable", "Disable alice@example.com", () => api.adminDisableUser, [ALICE]],
    ["enable", "Enable carol@example.com", () => api.adminEnableUser, [DISABLED_CAROL]],
    ["reset password", "Reset password for alice@example.com", () => api.adminResetUserPassword, [ALICE]],
  ] as const)("does not call the API for %s when the token has gone missing", async (_label, buttonName, getFn, users) => {
    await renderAdmin([...users]);
    const user = userEvent.setup();
    api.getToken.mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: buttonName }));
    expect(getFn()).not.toHaveBeenCalled();
  });
});

describe("AdminPage — header navigation", () => {
  it("logs out with the stored token and then replaces the route with /login", async () => {
    api.logout.mockResolvedValue(undefined);
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => expect(routerObj.replace).toHaveBeenCalledWith("/login"));
    expect(api.logout).toHaveBeenCalledWith("tok");
  });

  it("logs out with an empty token when none is stored", async () => {
    api.logout.mockResolvedValue(undefined);
    await renderAdmin();
    const user = userEvent.setup();
    api.getToken.mockReturnValue(null);
    await user.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => expect(routerObj.replace).toHaveBeenCalledWith("/login"));
    expect(api.logout).toHaveBeenCalledWith("");
  });

  it("navigates to the dashboard when Back to app is clicked", async () => {
    await renderAdmin();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /back to app/i }));
    expect(routerObj.push).toHaveBeenCalledWith("/dashboard");
  });
});
