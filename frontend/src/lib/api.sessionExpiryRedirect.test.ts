import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render } from "@testing-library/react";
import { createElement } from "react";
import { handleSessionExpiry } from "@/lib/api";
import { AuthSessionProvider } from "@/providers/AuthSessionProvider";

// @pytest.mark.issue("ISS-322") equivalent for vitest: this suite has no
// xfail primitive, so the failure itself (observed and recorded below) is
// the proof until ISS-322 lands. Remove this comment and the .fails marker
// on the `it` below once the fix ships.

// ─────────────────────────────────────────────────────────────────
// ISS-322 — a mid-session token expiry (the 401 ladder's handleSessionExpiry())
// must preserve the protected route the user was on, the same way the
// signed-out ?redirect= deep-link guard does. Today api.ts:147 navigates via
// routes.login({ expired: true }) with no redirect param at all, so re-login
// always lands on /dashboard. This test drives the real handleSessionExpiry()
// against a stubbed window.location and asserts the resulting navigation carries
// the original path+search as a redirect param. Since the dev merge the redirect
// itself is performed by AuthSessionProvider (the single session-expiry owner),
// so the provider is mounted here.
// ─────────────────────────────────────────────────────────────────

describe("handleSessionExpiry — ISS-322 preserves the original route", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    // jsdom's window.location is not directly assignable; replace it with a
    // plain mutable object so we can observe what handleSessionExpiry sets
    // href to, while reading a specific pathname/search as the "current page".
    // defineProperty, not assignment: `window.location` is typed non-writable, so
    // `window.location = {...}` is a type error however it is cast. Redefining the
    // property is the jsdom idiom and leaves the runtime behaviour identical.
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: {
        pathname: "/settings/ai-model",
        search: "",
        hash: "",
        href: "http://localhost/settings/ai-model",
        assign: vi.fn(),
      } as unknown as Location,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

    it("ISS-322 — attaches a redirect param pointing back at the protected route", () => {
    render(createElement(AuthSessionProvider, null, null));
    handleSessionExpiry();

    expect(window.location.assign).toHaveBeenCalledTimes(1);
    const href = vi.mocked(window.location.assign).mock.calls[0][0] as string;
    expect(href).toContain("expired=true");
    // This is the assertion that fails today: no `redirect` param is ever
    // built for the mid-session-expiry path.
    expect(decodeURIComponent(href)).toContain("redirect=/settings/ai-model");
  });
});
