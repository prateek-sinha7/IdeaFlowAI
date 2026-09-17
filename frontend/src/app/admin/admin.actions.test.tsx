/**
 * T14 — Admin page user actions: reset password, 409 last_admin handling,
 * 202 delete pending, and admin button visibility.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const { routerObj, api } = vi.hoisted(() => ({
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
    // Returns an unsubscribe function because the page uses it as a useEffect
    // cleanup; a bare vi.fn() would return undefined and React would throw on
    // unmount.
    onAdminMfaRequired: vi.fn(() => () => {}),
    ApiError: class ApiError extends Error {
      constructor(public status: number, public detail: unknown) {
        super();
      }
    },
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerObj,
}));

vi.mock("@/lib/api", () => api);

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
    id: "user-1",
    email: "alice@example.com",
    tier: "pro" as const,
    is_admin: false,
    status: "active" as const,
    created_at: "2026-01-15T09:00:00Z",
    workflow_run_count: 12,
  },
  {
    id: "user-2",
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

async function renderAsAdmin() {
  render(<AdminPage />);
  await screen.findByText("alice@example.com");
}

describe("AdminPage — T14 user actions", () => {
  describe("reset password action", () => {
    it("shows a reset password button for every user row", async () => {
      await renderAsAdmin();
      // Alice row should have key icon (reset password button)
      const aliceRow = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
      const resetButtons = within(aliceRow).getAllByRole("button");
      // Key button + disable button + delete button = at least 3 (may have more)
      expect(resetButtons.length).toBeGreaterThanOrEqual(1);
      // Verify there's a button with title containing "Reset password"
      expect(within(aliceRow).getByRole("button", { name: /reset password/i })).toBeInTheDocument();
    });

    it("on reset password success, shows 'Temporary password issued' toast", async () => {
      api.adminResetUserPassword.mockResolvedValue({
        status: "temporary_password_set",
      });
      await renderAsAdmin();
      const user = userEvent.setup();

      const aliceRow = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
      const resetButton = within(aliceRow).getByRole("button", { name: /reset password/i });
      await user.click(resetButton);

      await waitFor(() => {
        expect(screen.getByText(/temporary password issued.*change it at next login/i)).toBeInTheDocument();
      });
      expect(api.adminResetUserPassword).toHaveBeenCalledWith("tok", "user-1");
    });
  });

  describe("409 last_admin error handling", () => {
    it("on 409 with code='last_admin' from role removal, shows specific error message", async () => {
      const ApiError = api.ApiError;
      api.adminUpdateRole.mockRejectedValue(
        new ApiError(409, { code: "last_admin", detail: "Cannot remove the last administrator" })
      );
      await renderAsAdmin();
      const user = userEvent.setup();

      // Bob is an admin; try to remove admin access
      const bobRow = screen.getByText("bob@example.com").closest("tr") as HTMLElement;
      const roleButton = within(bobRow).getByRole("button", { name: /remove admin access/i });
      await user.click(roleButton);

      await waitFor(() => {
        expect(screen.getByText(/cannot remove the last administrator/i)).toBeInTheDocument();
      });
    });
  });

  describe("202 delete pending message", () => {
    it("on delete success, shows 'Cognito deletion is pending' message", async () => {
      api.adminDeleteUser.mockResolvedValue(undefined);
      await renderAsAdmin();
      const user = userEvent.setup();

      const aliceRow = screen.getByText("alice@example.com").closest("tr") as HTMLElement;
      const deleteButton = within(aliceRow).getByRole("button", { name: /delete alice@example\.com/i });
      await user.click(deleteButton);

      // Confirm deletion
      const confirmDelete = screen.getByRole("button", { name: /^delete$/i });
      await user.click(confirmDelete);

      await waitFor(() => {
        expect(screen.getByText(/cognito deletion is pending.*retried automatically/i)).toBeInTheDocument();
      });
    });
  });

  describe("admin button visibility (relying on server 409)", () => {
    it("shows disable/delete/demote buttons for all admins (no client-side hiding)", async () => {
      await renderAsAdmin();
      const bobRow = screen.getByText("bob@example.com").closest("tr") as HTMLElement;

      // Bob is an admin but we still show:
      // - Reset password button
      // - Disable button (should be visible even for admins)
      // - Delete button (should be visible even for admins)
      // - Demote button (clickable role pill)

      expect(within(bobRow).getByRole("button", { name: /reset password/i })).toBeInTheDocument();
      expect(within(bobRow).getByRole("button", { name: /disable bob@example\.com/i })).toBeInTheDocument();
      expect(within(bobRow).getByRole("button", { name: /delete bob@example\.com/i })).toBeInTheDocument();
      expect(within(bobRow).getByRole("button", { name: /remove admin access/i })).toBeInTheDocument();
    });

    it("allows attempting to disable an admin (server will enforce if needed)", async () => {
      api.adminDisableUser.mockResolvedValue({ ...USERS[1], status: "disabled" });
      await renderAsAdmin();
      const user = userEvent.setup();

      const bobRow = screen.getByText("bob@example.com").closest("tr") as HTMLElement;
      const disableButton = within(bobRow).getByRole("button", { name: /disable bob@example\.com/i });
      await user.click(disableButton);

      await waitFor(() => expect(api.adminDisableUser).toHaveBeenCalledWith("tok", "user-2"));
    });

    it("allows attempting to delete an admin (server will enforce if needed)", async () => {
      api.adminDeleteUser.mockResolvedValue(undefined);
      await renderAsAdmin();
      const user = userEvent.setup();

      const bobRow = screen.getByText("bob@example.com").closest("tr") as HTMLElement;
      const deleteButton = within(bobRow).getByRole("button", { name: /delete bob@example\.com/i });
      await user.click(deleteButton);

      const confirmDelete = screen.getByRole("button", { name: /^delete$/i });
      await user.click(confirmDelete);

      await waitFor(() => expect(api.adminDeleteUser).toHaveBeenCalledWith("tok", "user-2"));
    });
  });
});
