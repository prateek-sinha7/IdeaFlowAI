/**
 * AdminPage — toast auto-dismiss and replacement timing (ISS-324/ISS-487).
 *
 * Fake timers are installed AFTER the page has loaded (RTL's findBy/waitFor poll
 * with timers that vitest fakes), then advanced explicitly inside act().
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

const RESET_TOAST = "Temporary password issued; user must change it at next login.";

async function advance(ms: number) {
  await act(async () => { vi.advanceTimersByTime(ms); });
}

async function click(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("button", { name }));
  // let the mocked promise chain settle and React commit the toast
  for (let i = 0; i < 3; i++) await act(async () => { await Promise.resolve(); });
}

async function renderWithFakeTimers() {
  const { unmount } = render(<AdminPage />);
  await screen.findByText("alice@example.com");
  vi.useFakeTimers();
  // RTL only advances fake timers inside user-event's async wrapper when a global
  // jest with advanceTimersByTime exists; without it every user.click hangs.
  vi.stubGlobal("jest", { advanceTimersByTime: vi.advanceTimersByTime });
  return { user: userEvent.setup({ advanceTimers: vi.advanceTimersByTime }), unmount };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListUsers.mockResolvedValue([ALICE]);
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.adminResetUserPassword.mockResolvedValue({ status: "temporary_password_set" });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("AdminPage — toast timing", () => {
  it("dismisses a toast exactly 3500 ms after it appears", async () => {
    const { user } = await renderWithFakeTimers();
    await click(user, "Reset password for alice@example.com");
    expect(screen.getByText(RESET_TOAST)).toBeInTheDocument();

    await advance(3499);
    expect(screen.getByText(RESET_TOAST)).toBeInTheDocument();

    await advance(1);
    expect(screen.queryByText(RESET_TOAST)).toBeNull();
  });

  it("keeps a newer toast visible past the moment the older toast's timer would have fired", async () => {
    api.adminDisableUser.mockRejectedValue(new Error("Disable failed"));
    const { user } = await renderWithFakeTimers();

    await click(user, "Reset password for alice@example.com");
    await advance(2000);
    await click(user, "Disable alice@example.com");
    expect(screen.getByText("Disable failed")).toBeInTheDocument();
    expect(screen.queryByText(RESET_TOAST)).toBeNull();

    // t=4000 overall: the first toast's 3500 ms timer would already have fired.
    await advance(2000);
    expect(screen.getByText("Disable failed")).toBeInTheDocument();

    await advance(1499);
    expect(screen.getByText("Disable failed")).toBeInTheDocument();

    await advance(1);
    expect(screen.queryByText("Disable failed")).toBeNull();
  });

  it("does not throw when the page unmounts while a toast timer is pending", async () => {
    const { user, unmount } = await renderWithFakeTimers();
    await click(user, "Reset password for alice@example.com");
    expect(screen.getByText(RESET_TOAST)).toBeInTheDocument();

    unmount();

    await expect(advance(4000)).resolves.toBeUndefined();
  });
});
