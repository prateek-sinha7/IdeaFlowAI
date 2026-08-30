import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { handleSessionExpiry } from "@/lib/api";

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
// against a stubbed window.location and asserts the resulting href carries
// the original path+search as a redirect param.
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
        href: "http://localhost/settings/ai-model",
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
    handleSessionExpiry();

    const href = window.location.href;
    expect(href).toContain("expired=true");
    // This is the assertion that fails today: no `redirect` param is ever
    // built for the mid-session-expiry path.
    expect(decodeURIComponent(href)).toContain("redirect=/settings/ai-model");
  });
});
