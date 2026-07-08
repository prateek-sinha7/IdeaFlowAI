/**
 * useTabDeepLink — the nonce'd deep-link-into-tabs seam (open-design borrow #6,
 * Phase 31, CHATUI-01).
 *
 * Proves:
 *   1. requestOpenTab('preview') sets a pending {tab:'preview', nonce} with a
 *      fresh nonce;
 *   2. two successive requests to the SAME tab produce DIFFERENT nonces (a repeat
 *      deep-link re-triggers the consumer effect);
 *   3. consume() clears pending after read — single-use (a second consume yields
 *      nothing);
 *   4. a stale nonce (already consumed) does not re-open the tab.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useTabDeepLink } from "./useTabDeepLink";

describe("useTabDeepLink — nonce'd deep-link seam (borrow #6)", () => {
  it("Test 1: requestOpenTab sets a pending {tab, nonce} with a fresh nonce", () => {
    const { result } = renderHook(() => useTabDeepLink());
    expect(result.current.pending).toBeNull();

    act(() => {
      result.current.requestOpenTab("preview");
    });

    expect(result.current.pending).not.toBeNull();
    expect(result.current.pending?.tab).toBe("preview");
    expect(typeof result.current.pending?.nonce).toBe("number");
  });

  it("Test 2: two requests to the SAME tab produce DIFFERENT nonces", () => {
    const { result } = renderHook(() => useTabDeepLink());

    act(() => {
      result.current.requestOpenTab("preview");
    });
    const first = result.current.pending?.nonce;

    act(() => {
      result.current.requestOpenTab("preview");
    });
    const second = result.current.pending?.nonce;

    expect(first).toBeDefined();
    expect(second).toBeDefined();
    expect(second).not.toBe(first); // re-triggerable: a repeat deep-link re-fires
    expect(result.current.pending?.tab).toBe("preview");
  });

  it("Test 3: consume() clears pending after read — single-use", () => {
    const { result } = renderHook(() => useTabDeepLink());

    act(() => {
      result.current.requestOpenTab("files");
    });

    let taken: ReturnType<typeof result.current.consume> = null;
    act(() => {
      taken = result.current.consume();
    });

    expect(taken).not.toBeNull();
    expect(taken!.tab).toBe("files");
    expect(result.current.pending).toBeNull(); // cleared after read

    // A SECOND consume yields nothing (single-use).
    let again: ReturnType<typeof result.current.consume> = { tab: "x", nonce: -1 };
    act(() => {
      again = result.current.consume();
    });
    expect(again).toBeNull();
  });

  it("Test 4: a stale (already-consumed) nonce does not re-open the tab", () => {
    const { result } = renderHook(() => useTabDeepLink());

    act(() => {
      result.current.requestOpenTab("audit");
    });
    act(() => {
      result.current.consume();
    });

    // After consume, pending is null — a consumer effect keyed on `pending`
    // will not fire again for the stale target.
    expect(result.current.pending).toBeNull();

    // A fresh request still works (the seam is not permanently spent) and mints
    // a NEW nonce distinct from any prior one.
    act(() => {
      result.current.requestOpenTab("audit");
    });
    expect(result.current.pending?.tab).toBe("audit");
    expect(result.current.pending?.nonce).toBeGreaterThan(0);
  });
});
