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
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// next/navigation — LoginPage calls useRouter() and useSearchParams() at the top of the body.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// @/lib/api — never hit the transport from a render test (LOCK-B). The class is
// declared INSIDE the factory because vi.mock is hoisted above module scope.
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
  return { login: vi.fn(), ApiError };
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
