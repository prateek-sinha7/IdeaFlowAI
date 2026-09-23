/**
 * ISS-576 — the login page's forced-password-change form (Cognito
 * NEW_PASSWORD_REQUIRED challenge) must offer a show/hide toggle on its two
 * password fields, matching the affordance ISS-338 established for
 * /settings/profile's password fields.
 *
 * Today `page.tsx` hardcodes `type="password"` on both `#new-password` and
 * `#confirm-new-password` with no toggle button and no `Eye`/`EyeOff` import
 * anywhere in the file — see ISS-338's root cause (no shared masked-input
 * primitive) for why this recurs here.
 *
 * The NEW_PASSWORD_REQUIRED state cannot be staged end-to-end in the E2E
 * pool (no seeded account is parked in that Cognito challenge — see
 * `tests/integration/e2e/suites/01_auth/test_auth.py`'s `_CHALLENGE_BLOCKER`),
 * so this is a frontend render test: `login()` is mocked to resolve with an
 * `AuthChallengeResponse` the same way `login.reskin.test.tsx` mocks the
 * happy path, driving the page into the exact branch the bug lives in.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

beforeEach(() => {
  pushMock.mockClear();
  loginMock.mockReset();
  respondToLoginChallengeMock.mockReset();
  mockSearchParams.current = new URLSearchParams();
});

function signInIntoChallenge() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "temporary" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage — NEW_PASSWORD_REQUIRED challenge password visibility (ISS-576)", () => {
  it("ISS-576 — offers a show/hide toggle on both New password and Confirm password", async () => {
    loginMock.mockResolvedValue({
      challenge: "NEW_PASSWORD_REQUIRED",
      session: "opaque-session-token",
    });
    render(<LoginPage />);
    signInIntoChallenge();

    const newPasswordInput = await screen.findByLabelText("New password");
    const confirmPasswordInput = screen.getByLabelText("Confirm password");
    expect(newPasswordInput).toHaveAttribute("type", "password");
    expect(confirmPasswordInput).toHaveAttribute("type", "password");

    // A sibling reveal control, the same affordance ISS-338 established for
    // /settings/profile's Current/New password fields. Today neither exists.
    const newToggle = newPasswordInput.parentElement?.querySelector("button");
    const confirmToggle = confirmPasswordInput.parentElement?.querySelector("button");
    expect(newToggle, "New password has no show/hide toggle button").not.toBeNull();
    expect(confirmToggle, "Confirm password has no show/hide toggle button").not.toBeNull();
  });
});
