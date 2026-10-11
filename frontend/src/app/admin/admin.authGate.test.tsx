/**
 * AdminPage — auth gate and boot sequence (token check, getMe, admin-MFA
 * redirect, users loading/error/non-array states).
 *
 * Boundaries mocked: @/lib/api (transport), next/navigation, motion/react.
 * buildLoginRedirect / routes run for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import React from "react";

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

const USERS = [
  {
    id: "user-1",
    email: "alice@example.com",
    tier: "pro" as const,
    is_admin: false,
    status: "active" as const,
    created_at: "2026-01-15T12:00:00Z",
    workflow_run_count: 12,
  },
];

async function flush() {
  await act(async () => {});
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.pushState({}, "", "/admin");
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue(USERS);
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

afterEach(() => {
  window.history.pushState({}, "", "/");
});

describe("AdminPage — auth gate and boot", () => {
  it("redirects to login with the current path and skips all API calls when no token exists", async () => {
    api.getToken.mockReturnValue(null);
    render(<AdminPage />);
    await flush();
    expect(routerObj.replace).toHaveBeenCalledWith("/login?redirect=%2Fadmin");
    expect(api.getMe).not.toHaveBeenCalled();
    expect(api.adminListUsers).not.toHaveBeenCalled();
  });

  it("redirects to login when getMe rejects with a non-401 error", async () => {
    api.getMe.mockRejectedValue(new Error("network down"));
    render(<AdminPage />);
    await waitFor(() => expect(routerObj.replace).toHaveBeenCalledWith("/login?redirect=%2Fadmin"));
    expect(screen.queryByText("alice@example.com")).toBeNull();
  });

  it("does not redirect client-side when getMe rejects with a 401 ApiError", async () => {
    api.getMe.mockRejectedValue(new api.ApiError(401, "expired"));
    render(<AdminPage />);
    await waitFor(() => expect(api.getMe).toHaveBeenCalledWith("tok"));
    await flush();
    expect(routerObj.replace).not.toHaveBeenCalled();
  });

  it("redirects a non-admin to the dashboard without ever listing users", async () => {
    api.getMe.mockResolvedValue({ is_admin: false, email: "user@example.com" });
    render(<AdminPage />);
    await waitFor(() => expect(routerObj.replace).toHaveBeenCalledWith("/dashboard"));
    expect(api.adminListUsers).not.toHaveBeenCalled();
  });

  it("loads users with the stored token when the caller is an admin", async () => {
    render(<AdminPage />);
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(api.adminListUsers).toHaveBeenCalledWith("tok");
    expect(routerObj.replace).not.toHaveBeenCalled();
  });

  it("shows the loading indicator until the users request resolves", async () => {
    let resolveUsers: (value: typeof USERS) => void = () => {};
    api.adminListUsers.mockReturnValue(new Promise((resolve) => { resolveUsers = resolve; }));
    render(<AdminPage />);
    expect(await screen.findByText("Loading users...")).toBeInTheDocument();
    expect(screen.queryByText("alice@example.com")).toBeNull();

    await act(async () => { resolveUsers(USERS); });
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(screen.queryByText("Loading users...")).toBeNull();
  });

  it("shows an error toast and the empty state when loading users fails", async () => {
    api.adminListUsers.mockRejectedValue(new Error("boom"));
    render(<AdminPage />);
    expect(await screen.findByText("Failed to load users")).toBeInTheDocument();
    expect(screen.getByText("No users found")).toBeInTheDocument();
    expect(screen.queryByText("Loading users...")).toBeNull();
  });

  it("treats a non-array users response as an empty list", async () => {
    api.adminListUsers.mockResolvedValue(null);
    render(<AdminPage />);
    expect(await screen.findByText("No users found")).toBeInTheDocument();
  });

  it("redirects to the named enrolment view when admin MFA is required", async () => {
    const holder: { cb?: (detail: { enroll_path: string }) => void } = {};
    api.onAdminMfaRequired.mockImplementation((cb: (detail: { enroll_path: string }) => void) => {
      holder.cb = cb;
      return () => {};
    });
    render(<AdminPage />);
    await screen.findByText("alice@example.com");

    act(() => { holder.cb?.({ enroll_path: "/mfa/enroll?x=1&y=2" }); });

    expect(routerObj.replace).toHaveBeenCalledWith(
      "/settings/security?enroll=%2Fmfa%2Fenroll%3Fx%3D1%26y%3D2",
    );
  });

  it("unsubscribes from admin-MFA notifications when unmounted", async () => {
    const unsubscribe = vi.fn();
    api.onAdminMfaRequired.mockReturnValue(unsubscribe);
    const { unmount } = render(<AdminPage />);
    await screen.findByText("alice@example.com");
    expect(unsubscribe).not.toHaveBeenCalled();
    unmount();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });
});
