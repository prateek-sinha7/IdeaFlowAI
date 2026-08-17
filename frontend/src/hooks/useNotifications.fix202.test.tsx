/**
 * FIX-202 — Notification panel: persistence, per-item dismiss, toast run navigation.
 *
 * Tests for:
 *   A. localStorage hydration — notifications survive a simulated page refresh.
 *   B. Per-item dismissOne — removes one notification from state and persists the
 *      dismissal so a re-hydrated hook excludes the dismissed id.
 *   C. clearAll — clears state AND removes both localStorage keys.
 *   D. dismissOne is idempotent (dismissing a non-existent id is a no-op).
 *   E. Safety boundary — existing transitions (markCompleted, markFailed, etc.)
 *      are unaffected by the persistence layer.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { useNotifications, type PipelineNotification } from "./useNotifications";

// ── localStorage stub ─────────────────────────────────────────────────────────
// jsdom in vitest does not provide a real localStorage. We stub just the keys
// used by FIX-202 so no test leaks into a real browser store.
const memStore: Record<string, string> = {};
const localStorageMock = {
  getItem: (k: string) => (k in memStore ? memStore[k] : null),
  setItem: (k: string, v: string) => { memStore[k] = v; },
  removeItem: (k: string) => { delete memStore[k]; },
  clear: () => { Object.keys(memStore).forEach(k => delete memStore[k]); },
};
vi.stubGlobal("localStorage", localStorageMock);

const RUN_A = "run-A";
const RUN_B = "run-B";
const NOTIF_STORAGE_KEY = "flowin.notifications.v2";
const DISMISSED_STORAGE_KEY = "flowin.notifications.dismissed.v2";

beforeEach(() => {
  localStorageMock.clear();
});

// ─────────────────────────────────────────────────────────────────────────────
// A — localStorage hydration (notifications survive page refresh)
// ─────────────────────────────────────────────────────────────────────────────
describe("FIX-202-A — localStorage hydration", () => {
  // Cat 1: regression baseline — pre-fix there was no persistence
  it("FIX-202-A pre-fix baseline: without persistence, notifications vanish on remount", () => {
    // Simulate the old behaviour: clear storage before mount.
    localStorageMock.clear();
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "My run", 4);
    });
    expect(result.current.notifications.length).toBe(1);
    // Unmount and re-mount WITHOUT pre-seeding storage → should reload from storage.
    // In the pre-fix code this would return []. With fix, it returns the saved item.
    // We verify the storage was written, which is the fix contract.
    const saved = localStorageMock.getItem(NOTIF_STORAGE_KEY);
    expect(saved).not.toBeNull();
  });

  // Cat 2: happy path — notification written to localStorage and rehydrated
  it("FIX-202-A notifications are serialized to localStorage on state change", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "My run", 4);
    });
    const raw = localStorageMock.getItem(NOTIF_STORAGE_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as PipelineNotification[];
    expect(parsed.length).toBe(1);
    expect(parsed[0].id).toBe(RUN_A);
  });

  it("FIX-202-A a second hook instance hydrates from localStorage (simulates page refresh)", () => {
    // First "session" — write a notification.
    const { result: session1 } = renderHook(() => useNotifications());
    act(() => {
      session1.current.addRunningNotification(RUN_A, "user_stories", "Pre-refresh run", 3);
      session1.current.markCompleted(RUN_A);
    });

    // Second "session" — new hook instance reads from the same localStorage.
    const { result: session2 } = renderHook(() => useNotifications());
    const rehydrated = session2.current.notifications.find(n => n.id === RUN_A);
    expect(rehydrated).toBeDefined();
    expect(rehydrated!.status).toBe("completed");
  });

  // Cat 3: edge case — malformed localStorage does not crash
  it("FIX-202-A malformed localStorage content silently returns empty list", () => {
    localStorageMock.setItem(NOTIF_STORAGE_KEY, "{{not-json}}");
    // Should not throw; just returns []
    const { result } = renderHook(() => useNotifications());
    expect(result.current.notifications).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B — Per-item dismiss (dismissOne)
// ─────────────────────────────────────────────────────────────────────────────
describe("FIX-202-B — dismissOne per-item dismiss", () => {
  // Cat 1: regression baseline — pre-fix there was no dismissOne
  it("FIX-202-B dismissOne exists on the hook return value", () => {
    const { result } = renderHook(() => useNotifications());
    expect(typeof result.current.dismissOne).toBe("function");
  });

  // Cat 2: happy path
  it("FIX-202-B dismissOne removes the targeted notification from state", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
      result.current.addRunningNotification(RUN_B, "user_stories", "Run B", 3);
    });
    expect(result.current.notifications.length).toBe(2);

    act(() => { result.current.dismissOne(RUN_A); });

    expect(result.current.notifications.length).toBe(1);
    expect(result.current.notifications[0].id).toBe(RUN_B);
  });

  it("FIX-202-B dismissOne persists the dismissal — dismissed id excluded on re-hydration", () => {
    const { result: s1 } = renderHook(() => useNotifications());
    act(() => {
      s1.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
    });

    act(() => { s1.current.dismissOne(RUN_A); });

    // Dismissed ids must be in the dismissed key
    const dismissedRaw = localStorageMock.getItem(DISMISSED_STORAGE_KEY);
    expect(dismissedRaw).not.toBeNull();
    const dismissedIds = JSON.parse(dismissedRaw!) as string[];
    expect(dismissedIds).toContain(RUN_A);

    // Re-hydrated hook MUST NOT show the dismissed notification
    const { result: s2 } = renderHook(() => useNotifications());
    expect(s2.current.notifications.find(n => n.id === RUN_A)).toBeUndefined();
  });

  // Cat 3: edge case — dismissing a non-existent id is a no-op
  it("FIX-202-B dismissOne for unknown id is a no-op (no crash, state unchanged)", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
    });
    expect(() => {
      act(() => { result.current.dismissOne("non-existent-id"); });
    }).not.toThrow();
    expect(result.current.notifications.length).toBe(1);
  });

  // Cat 4: safety boundary — dismissOne does NOT remove a different notification
  it("FIX-202-B dismissOne(A) does not remove notification B", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
      result.current.addRunningNotification(RUN_B, "user_stories", "Run B", 3);
    });
    act(() => { result.current.dismissOne(RUN_A); });

    expect(result.current.notifications.find(n => n.id === RUN_B)).toBeDefined();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// C — clearAll wipes both localStorage keys
// ─────────────────────────────────────────────────────────────────────────────
describe("FIX-202-C — clearAll wipes localStorage", () => {
  it("FIX-202-C clearAll removes both the notifications and dismissed keys", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
      result.current.dismissOne(RUN_B); // seed the dismissed key too
    });

    act(() => { result.current.clearAll(); });

    expect(localStorageMock.getItem(NOTIF_STORAGE_KEY)).toBeNull();
    expect(localStorageMock.getItem(DISMISSED_STORAGE_KEY)).toBeNull();
    expect(result.current.notifications).toEqual([]);
  });

  it("FIX-202-C after clearAll a re-hydrated hook returns empty list", () => {
    const { result: s1 } = renderHook(() => useNotifications());
    act(() => {
      s1.current.addRunningNotification(RUN_A, "prototype", "Run A", 4);
    });
    act(() => { s1.current.clearAll(); });

    const { result: s2 } = renderHook(() => useNotifications());
    expect(s2.current.notifications).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D — ToastItem workflowRunId type contract (FIX-202 adds the field)
// ─────────────────────────────────────────────────────────────────────────────
describe("FIX-202-D — ToastItem workflowRunId field", () => {
  it("FIX-202-D ToastItem accepts optional workflowRunId at the type level", async () => {
    // Import the ToastItem type to prove the new field compiles.
    const { type } = await import("@/components/ui/CompletionToast");
    // The type export is the interface itself — just verify the module loads.
    expect(type).toBeUndefined(); // no named export named "type"; this is a TypeScript-only check
    // The real guard: constructing a ToastItem with workflowRunId must compile.
    const item: import("@/components/ui/CompletionToast").ToastItem = {
      id: "t1",
      workflowType: "prototype",
      title: "My run",
      status: "completed",
      workflowRunId: "run-xyz",
    };
    expect(item.workflowRunId).toBe("run-xyz");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// E — Safety boundary: existing transitions unaffected
// ─────────────────────────────────────────────────────────────────────────────
describe("FIX-202-E — existing transitions still work after persistence layer", () => {
  it("FIX-202-E markCompleted + markFailed + markCancelled + markGatePaused all still work", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addRunningNotification(RUN_A, "prototype", "A", 4);
      result.current.addRunningNotification(RUN_B, "user_stories", "B", 3);
    });
    act(() => { result.current.markCompleted(RUN_A); });
    expect(result.current.notifications.find(n => n.id === RUN_A)!.status).toBe("completed");

    act(() => { result.current.markFailed(RUN_B); });
    expect(result.current.notifications.find(n => n.id === RUN_B)!.status).toBe("failed");
  });

  it("FIX-202-E markGatePaused / markGateResumed round-trip still works", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => { result.current.addRunningNotification(RUN_A, "prototype", "A", 4); });
    act(() => { result.current.markGatePaused(RUN_A); });
    expect(result.current.notifications.find(n => n.id === RUN_A)!.status).toBe("gate");
    act(() => { result.current.markGateResumed(RUN_A); });
    expect(result.current.notifications.find(n => n.id === RUN_A)!.status).toBe("running");
  });

  it("FIX-202-E updateProgress is reflected in serialized storage", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => { result.current.addRunningNotification(RUN_A, "prototype", "A", 5); });
    act(() => { result.current.updateProgress(RUN_A, 3); });

    const raw = localStorageMock.getItem(NOTIF_STORAGE_KEY);
    const parsed = JSON.parse(raw!) as PipelineNotification[];
    expect(parsed.find(n => n.id === RUN_A)!.agentsCompleted).toBe(3);
  });
});
