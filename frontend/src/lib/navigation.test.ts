import { describe, it, expect, vi, afterEach } from "vitest";
import { goBackOr } from "./navigation";

function setHistoryLength(length: number) {
  Object.defineProperty(window.history, "length", { value: length, configurable: true });
}

afterEach(() => {
  setHistoryLength(1);
});

describe("goBackOr", () => {
  it("pops the previous entry instead of pushing a duplicate (ISS-741)", () => {
    setHistoryLength(3);
    const router = { back: vi.fn() };
    const fallback = vi.fn();

    goBackOr(router, fallback);

    expect(router.back).toHaveBeenCalledTimes(1);
    expect(fallback).not.toHaveBeenCalled();
  });

  it("falls back when there is no prior entry to pop", () => {
    setHistoryLength(1);
    const router = { back: vi.fn() };
    const fallback = vi.fn();

    goBackOr(router, fallback);

    expect(fallback).toHaveBeenCalledTimes(1);
    expect(router.back).not.toHaveBeenCalled();
  });
});
