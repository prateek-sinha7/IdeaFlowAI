import { beforeEach, describe, expect, it, vi } from "vitest";

type Guard = typeof import("./shallowNavGuard");

let guard: Guard;

beforeEach(async () => {
  // The guard keeps module-level state; reload it so tests stay independent.
  vi.resetModules();
  guard = await import("./shallowNavGuard");
});

describe("markShallowNav / consumeShallowNav (counter)", () => {
  it("consumes one mark per call and then returns false", () => {
    guard.markShallowNav();
    expect(guard.consumeShallowNav()).toBe(true);
    expect(guard.consumeShallowNav()).toBe(false);
  });

  it("is independent of the path-keyed marks", () => {
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNav()).toBe(false);
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
  });
});

describe("markShallowNavTo / consumeShallowNavTo (path-keyed)", () => {
  it("returns false when nothing was marked", () => {
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(false);
  });

  it("is one-shot", () => {
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(false);
  });

  it("is keyed by path: a different path neither consumes nor clears the mark", () => {
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNavTo("/workflows/w2/edit")).toBe(false);
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
  });

  it("ignores the query string and hash on both sides", () => {
    guard.markShallowNavTo("/workflows/w1/edit?ai=s1");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit?ai=s2#top")).toBe(true);
  });

  it("ignores a trailing slash on both sides", () => {
    guard.markShallowNavTo("/workflows/w1/edit/");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit/")).toBe(true);
  });

  it("keeps the root path distinct from other paths", () => {
    guard.markShallowNavTo("/");
    expect(guard.consumeShallowNavTo("/workflows")).toBe(false);
    expect(guard.consumeShallowNavTo("")).toBe(true);
  });

  it("counts repeated marks for the same path", () => {
    guard.markShallowNavTo("/workflows/w1/edit");
    guard.markShallowNavTo("/workflows/w1/edit");
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(true);
    expect(guard.consumeShallowNavTo("/workflows/w1/edit")).toBe(false);
  });
});
