/**
 * AdminPage — adversarial client behavior: hostile data rendering, redirect
 * construction, error-text exposure, token exposure.
 *
 * The UI is NOT a security boundary: backend authorization/IDOR tests for
 * /api/admin/* are required separately (pytest).
 */
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { act } from "react";
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

const HOSTILE_IMG = "<img src=x onerror=alert(1)>@evil.com";
const HOSTILE_SCRIPT = '"><script>x</script>@a.com';

function makeUser(email: string, id = "user-1"): AdminUser {
  return {
    id,
    email,
    tier: "basic",
    is_admin: false,
    status: "active",
    created_at: "2026-01-15T12:00:00Z",
    workflow_run_count: 0,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.history.pushState({}, "", "/admin");
  api.getToken.mockReturnValue("tok");
  api.getMe.mockResolvedValue({ is_admin: true, email: "admin@example.com" });
  api.adminListCapacity.mockResolvedValue({ instances: [] });
  api.onAdminMfaRequired.mockImplementation(() => () => {});
});

afterEach(() => {
  vi.restoreAllMocks();
  window.history.pushState({}, "", "/");
});

describe("AdminPage — security", () => {
  it("renders hostile emails as inert text in the table", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    api.adminListUsers.mockResolvedValue([makeUser(HOSTILE_IMG, "u1"), makeUser(HOSTILE_SCRIPT, "u2")]);
    const { container } = render(<AdminPage />);

    expect(await screen.findByText(HOSTILE_IMG)).toBeInTheDocument();
    expect(screen.getByText(HOSTILE_SCRIPT)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(alertSpy).not.toHaveBeenCalled();
  });

  it("renders a hostile email as inert text in the delete confirmation", async () => {
    api.adminListUsers.mockResolvedValue([makeUser(HOSTILE_SCRIPT)]);
    const { container } = render(<AdminPage />);
    await screen.findByText(HOSTILE_SCRIPT);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: `Delete ${HOSTILE_SCRIPT}` }));

    const modal = (await screen.findByRole("heading", { name: "Delete user?" })).parentElement as HTMLElement;
    expect(within(modal).getByText(HOSTILE_SCRIPT)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  it("renders a hostile email as inert text in the invitation toast", async () => {
    api.adminListUsers.mockResolvedValue([makeUser("alice@example.com")]);
    api.adminCreateUser.mockResolvedValue(makeUser(HOSTILE_SCRIPT, "u9"));
    const { container } = render(<AdminPage />);
    await screen.findByText("alice@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /add user/i }));
    await user.type(screen.getByLabelText("Email"), HOSTILE_SCRIPT);
    await user.click(screen.getByRole("button", { name: /send invitation/i }));

    expect(await screen.findByText(`Invited ${HOSTILE_SCRIPT}`)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  // Observed contract, flagged for a product decision: the toast forwards
  // `err.message` verbatim, so any server-side internal detail in an Error
  // message reaches the screen. Backend must keep messages sanitized.
  it("shows a rejected Error's message verbatim in the toast (internal detail would be exposed)", async () => {
    api.adminListUsers.mockResolvedValue([makeUser("alice@example.com")]);
    api.adminResetUserPassword.mockRejectedValue(new Error("SQL error at /srv/app/db.py line 12"));
    render(<AdminPage />);
    await screen.findByText("alice@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Reset password for alice@example.com" }));

    expect(await screen.findByText("SQL error at /srv/app/db.py line 12")).toBeInTheDocument();
  });

  it("encodes the full current location into the login redirect when unauthenticated", async () => {
    window.history.pushState({}, "", "/admin?x=1#h");
    api.getToken.mockReturnValue(null);
    render(<AdminPage />);
    await act(async () => {});

    expect(routerObj.replace).toHaveBeenCalledWith("/login?redirect=%2Fadmin%3Fx%3D1%23h");
  });

  it("keeps an external enroll_path inside the internal settings route as an encoded query value", async () => {
    const holder: { cb?: (detail: { enroll_path: string }) => void } = {};
    api.onAdminMfaRequired.mockImplementation((cb: (detail: { enroll_path: string }) => void) => {
      holder.cb = cb;
      return () => {};
    });
    api.adminListUsers.mockResolvedValue([makeUser("alice@example.com")]);
    render(<AdminPage />);
    await screen.findByText("alice@example.com");

    act(() => { holder.cb?.({ enroll_path: "https://evil.com/x&y=1" }); });

    expect(routerObj.replace).toHaveBeenCalledWith(
      "/settings/security?enroll=https%3A%2F%2Fevil.com%2Fx%26y%3D1",
    );
  });

  it("does not expose the bearer token anywhere in the rendered page", async () => {
    api.getToken.mockReturnValue("secret-token-xyz");
    api.adminListUsers.mockResolvedValue([makeUser("alice@example.com")]);
    render(<AdminPage />);
    await screen.findByText("alice@example.com");

    expect(document.body.innerHTML).not.toContain("secret-token-xyz");
  });
});
