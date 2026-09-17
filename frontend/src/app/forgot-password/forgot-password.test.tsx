/**
 * Cognito migration (Phase 5, `.kiro/specs/login/prompt.md`) — forgot-password
 * page render/behavior contract, over the existing backend flow (Decision 8,
 * `POST /api/auth/forgot-password[/confirm]`).
 *
 * Mirrors login.reskin.test.tsx's mocking conventions: next/navigation and
 * @/lib/api are stubbed so the page renders in jsdom with no router context
 * and no live transport (LOCK-B: no network).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}));

const { forgotPasswordMock, confirmForgotPasswordMock } = vi.hoisted(() => ({
  forgotPasswordMock: vi.fn(),
  confirmForgotPasswordMock: vi.fn(),
}));
// The mock ApiError class, declared via vi.hoisted (like `forgotPasswordMock`
// above) so it is available inside vi.mock's hoisted factory AND importable
// by tests that need to construct instances passing the page's
// `err instanceof ApiError` check.
const { MockApiError } = vi.hoisted(() => {
  class MockApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail?: unknown) {
      super("ApiError");
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }
  return { MockApiError };
});
vi.mock("@/lib/api", () => ({
  forgotPassword: forgotPasswordMock,
  confirmForgotPassword: confirmForgotPasswordMock,
  ApiError: MockApiError,
}));

// motion/react — strip animation-only props so motion.* render as plain nodes.
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
}));

import ForgotPasswordPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  forgotPasswordMock.mockReset();
  confirmForgotPasswordMock.mockReset();
});

describe("ForgotPasswordPage", () => {
  it("requests a code and advances to the confirm step on any resolved response (no account-existence signal)", async () => {
    forgotPasswordMock.mockResolvedValue({
      message: "If that account exists, a reset code has been sent.",
    });
    render(<ForgotPasswordPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset code/i }));

    await waitFor(() => expect(forgotPasswordMock).toHaveBeenCalledWith("a@b.com"));
    expect(await screen.findByLabelText(/reset code/i)).toBeInTheDocument();
  });

  it("shows the backend's 409 message instead of advancing when self-service reset is unavailable", async () => {
    forgotPasswordMock.mockRejectedValue(
      new MockApiError(
        409,
        "Self-service password reset is unavailable in this environment. Ask an administrator to reset your password.",
      ),
    );
    render(<ForgotPasswordPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset code/i }));

    await waitFor(() =>
      expect(screen.getByText(/ask an administrator/i)).toBeInTheDocument(),
    );
    // Must not have advanced to the confirm step.
    expect(screen.queryByLabelText(/reset code/i)).toBeNull();
  });

  it("rejects a new password under 12 characters before calling the backend", async () => {
    forgotPasswordMock.mockResolvedValue({ message: "ok" });
    render(<ForgotPasswordPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset code/i }));
    await screen.findByLabelText(/reset code/i);

    fireEvent.change(screen.getByLabelText(/reset code/i), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    expect(await screen.findByText(/at least 12 characters/i)).toBeInTheDocument();
    expect(confirmForgotPasswordMock).not.toHaveBeenCalled();
  });

  it("completes the reset and redirects to /login on success", async () => {
    forgotPasswordMock.mockResolvedValue({ message: "ok" });
    confirmForgotPasswordMock.mockResolvedValue({ message: "Password reset successfully. Please sign in." });
    render(<ForgotPasswordPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset code/i }));
    await screen.findByLabelText(/reset code/i);

    fireEvent.change(screen.getByLabelText(/reset code/i), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a-long-enough-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "a-long-enough-password" } });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() =>
      expect(confirmForgotPasswordMock).toHaveBeenCalledWith("a@b.com", "123456", "a-long-enough-password"),
    );
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
  });
});
