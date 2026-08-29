/**
 * BUG-20260828-041815-login-expired-1 — failed-login / session-expiry / challenge
 * error banners render with no ARIA live region or alert role, so screen readers
 * never announce them.
 *
 * ISS-337 — main sign-in form's `error` banner (page.tsx:271-279).
 * ISS-574 — `isExpired` session-expiry banner (page.tsx:261-269).
 * ISS-575 — `ChallengeForm`'s own error banner (page.tsx:446-450).
 *
 * Mocking idiom copied from ./login.reskin.test.tsx (next/navigation + @/lib/api
 * + motion/react stubs) so the page renders in jsdom with no live transport.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";

const { pushMock, mockSearchParams } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  mockSearchParams: { current: new URLSearchParams() },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => mockSearchParams.current,
}));

const { loginMock, respondToLoginChallengeMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  respondToLoginChallengeMock: vi.fn(),
}));
vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status: number;
    detail: unknown;
    constructor(status: number, detail?: unknown) {
      super("ApiError");
      this.status = status;
      this.detail = detail;
    }
  }
  function isAuthChallenge(data: unknown): boolean {
    return Boolean(data && typeof data === "object" && "challenge" in data);
  }
  return {
    getToken: () => null,
    login: loginMock,
    respondToLoginChallenge: respondToLoginChallengeMock,
    isAuthChallenge,
    ApiError,
  };
});

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

import LoginPage from "./page";
import { ApiError } from "@/lib/api";

beforeEach(() => {
  pushMock.mockClear();
  loginMock.mockReset();
  respondToLoginChallengeMock.mockReset();
  mockSearchParams.current = new URLSearchParams();
});

function hasLiveRegionSemantics(el: Element): boolean {
  if (el.getAttribute("role") === "alert" || el.getAttribute("role") === "status") return true;
  const live = el.getAttribute("aria-live");
  if (live === "polite" || live === "assertive") return true;
  return el.closest('[role="alert"], [role="status"], [aria-live="polite"], [aria-live="assertive"]') !== null;
}

describe("BUG-20260828-041815-login-expired-1 — error banners must be announced to screen readers", () => {
  it("ISS-337: the failed-login error banner has role=alert/status or aria-live", async () => {
    loginMock.mockRejectedValue(new ApiError(401, null));
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "wrong@flowinqa.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongpass" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const banner = await screen.findByText("Invalid email or password.");
    expect(hasLiveRegionSemantics(banner)).toBe(true);
  });

  it("ISS-574: the isExpired session-expiry banner has role=alert/status or aria-live", () => {
    mockSearchParams.current = new URLSearchParams("expired=true");
    render(<LoginPage />);

    const banner = screen.getByText("Your session expired. Please sign in again.");
    expect(hasLiveRegionSemantics(banner)).toBe(true);
  });

  it("ISS-575: ChallengeForm's own error banner has role=alert/status or aria-live", async () => {
    loginMock.mockResolvedValue({
      challenge: "NEW_PASSWORD_REQUIRED",
      session: "sess-token",
    });
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "tempPass123" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    // Land on the "Set a new password" challenge step.
    await screen.findByLabelText("New password");

    // Trigger the client-side "Passwords do not match." validation error.
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "abcdefghijkl" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "mismatched123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    const banner = await screen.findByText("Passwords do not match.");
    expect(hasLiveRegionSemantics(banner)).toBe(true);
  });
});
