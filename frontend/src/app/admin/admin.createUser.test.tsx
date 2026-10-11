/**
 * AdminPage — create-user (invitation) modal: email gating, submit, in-flight,
 * failure, close paths. EMAIL_PATTERN is module-private and is exercised via the
 * submit button's enabled state.
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
const CREATED: AdminUser = {
  id: "user-9",
  email: "new@example.com",
  tier: "basic",
  is_admin: false,
  status: "active",
  created_at: "2026-03-01T12:00:00Z",
  workflow_run_count: 0,
};

async function openModal() {
  render(<AdminPage />);
  await screen.findByText("alice@example.com");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /add user/i }));
  await screen.findByRole("heading", { name: "Create New User" });
  return user;
}

const submitButton = () => screen.getByRole("button", { name: /send invitation|sending invite/i });

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue([ALICE]);
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

describe("AdminPage — create user modal", () => {
  it("closes when the close (X) button is clicked", async () => {
    const user = await openModal();
    // The X button has no accessible name (a11y finding); it is the only button
    // in the modal header next to the heading.
    const header = screen.getByRole("heading", { name: "Create New User" }).parentElement as HTMLElement;
    await user.click(within(header).getByRole("button"));
    expect(screen.queryByRole("heading", { name: "Create New User" })).toBeNull();
  });

  it("closes when the backdrop is clicked", async () => {
    const user = await openModal();
    // Backdrop is an unlabeled div: first child of the fixed overlay wrapper.
    const overlay = screen.getByRole("heading", { name: "Create New User" }).closest("div.fixed") as HTMLElement;
    await user.click(overlay.firstElementChild as HTMLElement);
    expect(screen.queryByRole("heading", { name: "Create New User" })).toBeNull();
  });

  it.each([
    ["empty", ""],
    ["no at-sign", "plainaddress"],
    ["no dot in domain", "a@b"],
    ["contains whitespace", "a b@c.com"],
    ["missing local part", "@c.com"],
  ])("keeps the submit button disabled when the email is %s", async (_label, email) => {
    const user = await openModal();
    if (email) await user.type(screen.getByLabelText("Email"), email);
    expect(submitButton()).toBeDisabled();
  });

  it("enables the submit button for a well-formed email", async () => {
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    expect(submitButton()).toBeEnabled();
  });

  it("offers the four plans labelled by tier name", async () => {
    await openModal();
    const select = screen.getByRole("combobox", { name: /select plan tier/i });
    const labels = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(labels).toEqual(["Basic", "Pro", "Enterprise", "Hexaware"]);
  });

  it("invites the user, prepends the row, closes the modal and toasts on success", async () => {
    api.adminCreateUser.mockResolvedValue(CREATED);
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(submitButton());

    expect(await screen.findByText("Invited new@example.com")).toBeInTheDocument();
    expect(api.adminCreateUser).toHaveBeenCalledWith("tok", "new@example.com", "basic", false);
    expect(screen.queryByRole("heading", { name: "Create New User" })).toBeNull();
    const dataRows = screen.getAllByRole("row").slice(1);
    expect(within(dataRows[0]).getByText("new@example.com")).toBeInTheDocument();
    expect(within(dataRows[1]).getByText("alice@example.com")).toBeInTheDocument();
  });

  it("resets the form after a successful invitation", async () => {
    api.adminCreateUser.mockResolvedValue(CREATED);
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.selectOptions(screen.getByRole("combobox", { name: /select plan tier/i }), "enterprise");
    await user.click(screen.getByRole("checkbox", { name: "Grant admin access" }));
    await user.click(submitButton());
    await screen.findByText("Invited new@example.com");

    await user.click(screen.getByRole("button", { name: /add user/i }));

    expect(await screen.findByLabelText("Email")).toHaveValue("");
    expect(screen.getByRole("combobox", { name: /select plan tier/i })).toHaveValue("basic");
    expect(screen.getByRole("checkbox", { name: "Grant admin access" })).not.toBeChecked();
  });

  it("sends the chosen plan and admin flag", async () => {
    api.adminCreateUser.mockResolvedValue({ ...CREATED, tier: "enterprise", is_admin: true });
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.selectOptions(screen.getByRole("combobox", { name: /select plan tier/i }), "enterprise");
    await user.click(screen.getByRole("checkbox", { name: "Grant admin access" }));
    await user.click(submitButton());

    await waitFor(() =>
      expect(api.adminCreateUser).toHaveBeenCalledWith("tok", "new@example.com", "enterprise", true),
    );
  });

  it("disables the button and relabels it while the invitation is in flight", async () => {
    let resolveCreate: (value: AdminUser) => void = () => {};
    api.adminCreateUser.mockReturnValue(new Promise((resolve) => { resolveCreate = resolve; }));
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(submitButton());

    const pending = screen.getByRole("button", { name: "Sending invite..." });
    expect(pending).toBeDisabled();
    await user.click(pending);
    expect(api.adminCreateUser).toHaveBeenCalledTimes(1);

    await act(async () => { resolveCreate(CREATED); });
    await screen.findByText("Invited new@example.com");
  });

  it("keeps the modal open, preserves the email and shows the error when creation fails", async () => {
    api.adminCreateUser.mockRejectedValue(new Error("Email already exists"));
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(submitButton());

    expect(await screen.findByText("Email already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveValue("new@example.com");
    expect(submitButton()).toBeEnabled();
  });

  it("falls back to a generic toast when creation rejects with a non-Error", async () => {
    api.adminCreateUser.mockRejectedValue("nope");
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(submitButton());

    expect(await screen.findByText("Failed to create user")).toBeInTheDocument();
  });

  it("does not call the API when the token has gone missing at submit time", async () => {
    const user = await openModal();
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    api.getToken.mockReturnValue(null);
    await user.click(submitButton());

    expect(api.adminCreateUser).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Create New User" })).toBeInTheDocument();
  });
});
