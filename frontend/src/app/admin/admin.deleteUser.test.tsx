/**
 * AdminPage — delete-user confirmation flow and ApiError branches.
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

const DELETE_ERROR_TOAST = "Failed to delete user";
const LAST_ADMIN_TOAST = "Cannot remove the last administrator.";
const PENDING_TOAST = "User removed. Cognito deletion is pending and will be retried automatically.";

function rowOf(email: string): HTMLElement {
  return screen.getByText(email).closest("tr") as HTMLElement;
}

const confirmModal = () =>
  screen.getByRole("heading", { name: "Delete user?" }).parentElement as HTMLElement;
const confirmDelete = () => within(confirmModal()).getByRole("button", { name: "Delete" });

async function openConfirm(email = "alice@example.com") {
  const user = userEvent.setup();
  await user.click(within(rowOf(email)).getByRole("button", { name: `Delete ${email}` }));
  await screen.findByRole("heading", { name: "Delete user?" });
  return user;
}

async function renderAdmin(users: AdminUser[] = [ALICE, BOB]) {
  api.adminListUsers.mockResolvedValue(users);
  render(<AdminPage />);
  await screen.findByText(users[0].email || "Total Users");
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

describe("AdminPage — delete user", () => {
  it("asks for confirmation naming the account before deleting anything", async () => {
    await renderAdmin();
    await openConfirm();
    expect(within(confirmModal()).getByText("alice@example.com")).toBeInTheDocument();
    expect(api.adminDeleteUser).not.toHaveBeenCalled();
  });

  it("shows a placeholder in the confirmation when the account has no email", async () => {
    await renderAdmin([makeNoEmailUser()]);
    const user = userEvent.setup();
    const row = screen.getByText("cccc3333…").closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("(no email)")).toBeInTheDocument();
  });

  it("closes without calling the API when Cancel is clicked", async () => {
    await renderAdmin();
    const user = await openConfirm();
    await user.click(within(confirmModal()).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("heading", { name: "Delete user?" })).toBeNull();
    expect(api.adminDeleteUser).not.toHaveBeenCalled();
  });

  it("closes without calling the API when the backdrop is clicked", async () => {
    await renderAdmin();
    const user = await openConfirm();
    // Unlabeled backdrop div: first child of the fixed overlay wrapper.
    const overlay = confirmModal().closest("div.fixed") as HTMLElement;
    await user.click(overlay.firstElementChild as HTMLElement);
    expect(screen.queryByRole("heading", { name: "Delete user?" })).toBeNull();
    expect(api.adminDeleteUser).not.toHaveBeenCalled();
  });

  it("removes the row, updates stats, closes the modal and toasts on success", async () => {
    api.adminDeleteUser.mockResolvedValue(undefined);
    await renderAdmin();
    const user = await openConfirm();
    await user.click(confirmDelete());

    expect(await screen.findByText(PENDING_TOAST)).toBeInTheDocument();
    expect(api.adminDeleteUser).toHaveBeenCalledWith("tok", "user-1");
    expect(screen.queryByText("alice@example.com")).toBeNull();
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Delete user?" })).toBeNull();
    expect(screen.getByText("Total Users", { selector: "p" }).nextElementSibling).toHaveTextContent("1");
  });

  it("treats an ApiError 202 as success: toasts and closes but keeps the row listed", async () => {
    api.adminDeleteUser.mockRejectedValue(new api.ApiError(202, "accepted"));
    await renderAdmin();
    const user = await openConfirm();
    await user.click(confirmDelete());

    expect(await screen.findByText(PENDING_TOAST)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Delete user?" })).toBeNull();
    // Observed current behavior: the row is not removed on a 202.
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("keeps the modal and row and shows the last-admin message on a 409 last_admin", async () => {
    api.adminDeleteUser.mockRejectedValue(new api.ApiError(409, { code: "last_admin" }));
    await renderAdmin();
    const user = await openConfirm("bob@example.com");
    await user.click(confirmDelete());

    expect(await screen.findByText(LAST_ADMIN_TOAST)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Delete user?" })).toBeInTheDocument();
    expect(screen.getByText("bob@example.com", { selector: "p.text-ink-900" })).toBeInTheDocument();
  });

  it.each([
    ["409 with another code", () => new api.ApiError(409, { code: "other" })],
    ["409 with a string detail", () => new api.ApiError(409, "conflict")],
    ["500 server error", () => new api.ApiError(500, "boom", "server exploded")],
    ["plain Error", () => new Error("kaput")],
    ["non-Error rejection", () => "nope"],
  ])("shows a generic failure toast and keeps the modal open on %s", async (_label, makeError) => {
    api.adminDeleteUser.mockRejectedValue(makeError());
    await renderAdmin();
    const user = await openConfirm();
    await user.click(confirmDelete());

    expect(await screen.findByText(DELETE_ERROR_TOAST)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Delete user?" })).toBeInTheDocument();
    // Raw error text is not leaked into the toast on this path.
    expect(screen.queryByText("server exploded")).toBeNull();
    expect(screen.queryByText("kaput")).toBeNull();
  });

  it("calls the API once and disables Delete while the request is in flight", async () => {
    let resolveDelete: () => void = () => {};
    api.adminDeleteUser.mockReturnValue(new Promise<void>((resolve) => { resolveDelete = resolve; }));
    await renderAdmin();
    const user = await openConfirm();

    await user.dblClick(confirmDelete());

    expect(api.adminDeleteUser).toHaveBeenCalledTimes(1);
    expect(confirmDelete()).toBeDisabled();

    await act(async () => { resolveDelete(); });
    expect(await screen.findByText(PENDING_TOAST)).toBeInTheDocument();
    expect(screen.queryByText(DELETE_ERROR_TOAST)).toBeNull();
  });

  it("does not call the API when the token has gone missing at confirm time", async () => {
    await renderAdmin();
    const user = await openConfirm();
    api.getToken.mockReturnValue(null);
    await user.click(confirmDelete());

    await waitFor(() => expect(api.getToken).toHaveBeenCalled());
    expect(api.adminDeleteUser).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Delete user?" })).toBeInTheDocument();
  });
});

function makeNoEmailUser(): AdminUser {
  return { ...ALICE, id: "cccc3333-0000-0000-0000-000000000000", email: "" };
}
