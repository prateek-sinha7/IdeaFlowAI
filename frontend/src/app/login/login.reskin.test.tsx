/**
 * Phase 35 / 35-06 (B1-05, ND-12) — login reskin render contract.
 *
 * The login page is being reskinned onto the Phase-32 token layer with a NEW
 * two-column layout: a ~46% dark brand panel on the left + the fully-wired form
 * on the right. This test is the RED->GREEN gate for that reskin AND a
 * regression guard on the e2e selectors the mocked `ts-a.auth.spec.ts` depends
 * on.
 *
 * Two things are asserted together:
 *
 *  1. RESKIN STATE (RED now, GREEN after the page is reskinned):
 *       - a dark brand panel element is present (near-black surface + wordmark);
 *       - NO "Continue with SSO" button and NO "Forgot" link render — the
 *         identity traps are DROPPED (no backend exists for them, ND-12).
 *
 *  2. SELECTOR PRESERVATION (must stay green across the reskin):
 *       - `#email` + `#password` inputs exist;
 *       - the submit control's accessible name is exactly "Sign in";
 *       - the heading text "Welcome back" is present.
 *
 * next/navigation + @/lib/api are stubbed so the client page renders in jsdom
 * without a router context or a live transport (LOCK-B: no network).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// next/navigation — LoginPage calls useRouter() + useSearchParams() at the top
// of the body (the latter to read the post-login ?redirect= target).
const { pushMock, mockSearchParams } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  mockSearchParams: { current: new URLSearchParams() },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => mockSearchParams.current,
}));

// @/lib/api — never hit the transport from a render test (LOCK-B). The class is
// declared INSIDE the factory because vi.mock is hoisted above module scope.
//
// Cognito migration (Phase 4): the page now also imports
// `respondToLoginChallenge` + `isAuthChallenge` (the challenge-response path).
// `isAuthChallenge` is real logic (a type guard keyed on the `challenge` field
// presence), not network I/O, so it is safe — and necessary — to keep the real
// implementation here rather than stub it; every test in this file resolves
// `loginMock` with a plain AuthResponse (no `challenge` field), so
// `isAuthChallenge` always returns false and the existing flows are untouched.
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
    login: loginMock,
    respondToLoginChallenge: respondToLoginChallengeMock,
    isAuthChallenge,
    ApiError,
  };
});

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
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import LoginPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  loginMock.mockReset();
  mockSearchParams.current = new URLSearchParams();
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret123" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage — post-login routing", () => {
  it("routes to the main application by default (no ?redirect=)", async () => {
    loginMock.mockResolvedValue({
      token: "tok",
      user: { id: "1", email: "a@b.com", tier: "basic", is_admin: false },
    });
    render(<LoginPage />);
    fillAndSubmit();
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });

  it("routes an admin to the main application too — no automatic admin redirect", async () => {
    loginMock.mockResolvedValue({
      token: "tok",
      user: { id: "1", email: "admin@b.com", tier: "basic", is_admin: true },
    });
    render(<LoginPage />);
    fillAndSubmit();
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });

  it("returns to the originally-requested internal page via ?redirect=", async () => {
    mockSearchParams.current = new URLSearchParams("redirect=%2Fworkflow%2Fcreate%3Fmode%3Dppt");
    loginMock.mockResolvedValue({
      token: "tok",
      user: { id: "1", email: "a@b.com", tier: "basic", is_admin: false },
    });
    render(<LoginPage />);
    fillAndSubmit();
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/workflow/create?mode=ppt"));
  });

  it("ignores an external/malformed ?redirect= and falls back to the main application", async () => {
    mockSearchParams.current = new URLSearchParams("redirect=" + encodeURIComponent("https://evil.com"));
    loginMock.mockResolvedValue({
      token: "tok",
      user: { id: "1", email: "a@b.com", tier: "basic", is_admin: false },
    });
    render(<LoginPage />);
    fillAndSubmit();
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });
});

describe("LoginPage reskin — brand panel + selector-preservation contract", () => {
  it("renders #email and #password inputs (selectors preserved)", () => {
    const { container } = render(<LoginPage />);
    expect(container.querySelector("#email")).not.toBeNull();
    expect(container.querySelector("#password")).not.toBeNull();
  });

  it('the submit control has accessible name exactly "Sign in"', () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it('renders the heading "Welcome back"', () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("heading", { name: "Welcome back" }),
    ).toBeInTheDocument();
  });

  it("renders a dark brand panel (near-black surface + wordmark)", () => {
    render(<LoginPage />);
    const panel = screen.getByTestId("login-brand-panel");
    expect(panel).toBeInTheDocument();
    // The panel is the dark near-black surface (mirrors the 35-01 shell idiom).
    expect(panel.className).toContain("bg-surface-near-black");
    // ...and carries the product wordmark.
    expect(panel.textContent).toMatch(/VelocityAI/);
  });

  it("does NOT render SSO / Forgot identity traps (dropped — no backend)", () => {
    render(<LoginPage />);
    expect(screen.queryByRole("button", { name: /sso/i })).toBeNull();
    expect(screen.queryByText(/continue with sso/i)).toBeNull();
    expect(screen.queryByText(/forgot/i)).toBeNull();
  });
});
