import { describe, it, expect } from "vitest";
import {
  isSafeRedirectPath,
  resolveRedirectTarget,
  buildLoginRedirect,
  DEFAULT_POST_LOGIN_ROUTE,
} from "./authRedirect";

describe("isSafeRedirectPath", () => {
  it("accepts internal app paths", () => {
    expect(isSafeRedirectPath("/dashboard")).toBe(true);
    expect(isSafeRedirectPath("/admin")).toBe(true);
    expect(isSafeRedirectPath("/workflow/create?mode=ppt")).toBe(true);
    expect(isSafeRedirectPath("/dashboard#section")).toBe(true);
  });

  it("rejects absolute/external URLs", () => {
    expect(isSafeRedirectPath("https://evil.com")).toBe(false);
    expect(isSafeRedirectPath("http://evil.com/dashboard")).toBe(false);
  });

  it("rejects protocol-relative URLs (open-redirect vector)", () => {
    expect(isSafeRedirectPath("//evil.com")).toBe(false);
    expect(isSafeRedirectPath("//evil.com/dashboard")).toBe(false);
  });

  it("rejects backslash tricks browsers normalize to protocol-relative", () => {
    expect(isSafeRedirectPath("/\\evil.com")).toBe(false);
  });

  it("rejects empty/missing/non-rooted values", () => {
    expect(isSafeRedirectPath(null)).toBe(false);
    expect(isSafeRedirectPath(undefined)).toBe(false);
    expect(isSafeRedirectPath("")).toBe(false);
    expect(isSafeRedirectPath("dashboard")).toBe(false);
  });

  it("rejects values with leading control characters", () => {
    expect(isSafeRedirectPath("\t/evil.com")).toBe(false);
  });
});

describe("resolveRedirectTarget", () => {
  it("returns the candidate when safe", () => {
    expect(resolveRedirectTarget("/admin")).toBe("/admin");
  });

  it("falls back to the default main-app route for anything unsafe/absent", () => {
    expect(resolveRedirectTarget(null)).toBe(DEFAULT_POST_LOGIN_ROUTE);
    expect(resolveRedirectTarget("https://evil.com")).toBe(DEFAULT_POST_LOGIN_ROUTE);
    expect(resolveRedirectTarget("//evil.com")).toBe(DEFAULT_POST_LOGIN_ROUTE);
  });
});

describe("buildLoginRedirect", () => {
  it("carries the current internal path+query+hash as ?redirect=", () => {
    window.history.pushState({}, "", "/workflow/create?mode=ppt#step2");
    expect(buildLoginRedirect()).toBe(
      `/login?redirect=${encodeURIComponent("/workflow/create?mode=ppt#step2")}`,
    );
  });

  it("degrades to a bare /login for the root path", () => {
    window.history.pushState({}, "", "/");
    expect(buildLoginRedirect()).toBe(`/login?redirect=${encodeURIComponent("/")}`);
  });
});
