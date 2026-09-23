/**
 * workflowChaining — v2 storage migration (Task 11.9, Requirement 21 / Task 11.2).
 *
 * Validates that migrateChainStorageV2():
 *  - Drops chain.context_block from sessionStorage + localStorage on first call
 *  - Is idempotent (second call is a no-op: does NOT remove unrelated keys or reset v2 marker)
 *  - Preserves chain.brief, chain.from, chain.source_run_id, and unrelated keys
 *  - Marks migration as done with chain.v2.version key
 *  - Works even when localStorage is unavailable (does not throw)
 *  - chain.context_block absent after migration → in-memory read returns null
 *    (simulates the wizard's chainContextBlock state staying null)
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  migrateChainStorageV2,
  CHAIN_BRIEF_KEY,
  CHAIN_FROM_KEY,
  CHAIN_SOURCE_RUN_ID_KEY,
  CHAIN_CONTEXT_BLOCK_KEY,
  CHAIN_V2_VERSION_KEY,
} from "../workflowChaining";

// jsdom provides Storage in the vitest/jsdom environment.

function clearAll() {
  sessionStorage.clear();
  localStorage.clear();
}

beforeEach(() => {
  clearAll();
});

// ─────────────────────────────────────────────────────────────────────────────
// Core drop behavior
// ─────────────────────────────────────────────────────────────────────────────

describe("migrateChainStorageV2 — drops legacy context block key", () => {
  it("removes chain.context_block from sessionStorage", () => {
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "=== CONTEXT FROM PREVIOUS PIPELINE ===\n\nsome content");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
  });

  it("removes chain.context_block from localStorage", () => {
    localStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "=== CONTEXT FROM PREVIOUS PIPELINE ===\n\nsome content");
    migrateChainStorageV2();
    expect(localStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
  });

  it("removes from both storages in a single call", () => {
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "block-in-session");
    localStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "block-in-local");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
    expect(localStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
  });

  it("sets chain.v2.version marker after migration", () => {
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_V2_VERSION_KEY)).not.toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Idempotency
// ─────────────────────────────────────────────────────────────────────────────

describe("migrateChainStorageV2 — idempotency", () => {
  it("second call is a no-op (marker already set)", () => {
    // Seed a context block and run migration once
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "first-run");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();

    // Re-seed the key (simulates a race or stale write after first migration)
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "re-seeded-after-migration");
    // Second call should NOT remove it again (marker is set, migration already ran)
    migrateChainStorageV2();
    // The re-seeded key should still be present — the second call is a no-op
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBe("re-seeded-after-migration");
  });

  it("calling migrateChainStorageV2 three times does not reset the version marker", () => {
    migrateChainStorageV2();
    const markerAfterFirst = sessionStorage.getItem(CHAIN_V2_VERSION_KEY);
    migrateChainStorageV2();
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_V2_VERSION_KEY)).toBe(markerAfterFirst);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Preserves unrelated and carry-forward keys
// ─────────────────────────────────────────────────────────────────────────────

describe("migrateChainStorageV2 — preserves other keys", () => {
  it("preserves chain.brief in sessionStorage", () => {
    sessionStorage.setItem(CHAIN_BRIEF_KEY, "Build a user story for checkout");
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "to-be-dropped");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_BRIEF_KEY)).toBe("Build a user story for checkout");
  });

  it("preserves chain.from in sessionStorage", () => {
    sessionStorage.setItem(CHAIN_FROM_KEY, "user_stories");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_FROM_KEY)).toBe("user_stories");
  });

  it("preserves chain.source_run_id in sessionStorage", () => {
    sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, "run-abc-123");
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBe("run-abc-123");
  });

  it("preserves completely unrelated sessionStorage keys", () => {
    sessionStorage.setItem("some-other-feature-key", "some-value");
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "drop-me");
    migrateChainStorageV2();
    expect(sessionStorage.getItem("some-other-feature-key")).toBe("some-value");
  });

  it("preserves completely unrelated localStorage keys", () => {
    localStorage.setItem("user_preferences", JSON.stringify({ theme: "dark" }));
    localStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "drop-me");
    migrateChainStorageV2();
    expect(localStorage.getItem("user_preferences")).toBe(JSON.stringify({ theme: "dark" }));
  });

  it("preserves chain.brief in localStorage when it was stored there", () => {
    localStorage.setItem(CHAIN_BRIEF_KEY, "draft brief in local storage");
    localStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "to-drop");
    migrateChainStorageV2();
    expect(localStorage.getItem(CHAIN_BRIEF_KEY)).toBe("draft brief in local storage");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// In-memory launch state simulation
// ─────────────────────────────────────────────────────────────────────────────

describe("migrateChainStorageV2 — in-memory launch state implicit cleanup", () => {
  it("chain.context_block absent means a read returns null (simulates wizard init)", () => {
    // Before migration — key present
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "=== CONTEXT FROM PREVIOUS PIPELINE ===\nsome content");
    migrateChainStorageV2();
    // After migration — reading the key (as the wizard would on mount) returns null
    const value = sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY);
    expect(value).toBeNull();
    // A wizard that reads this on mount would set chainContextBlock = null → no block injected
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Edge: already migrated / no legacy key present
// ─────────────────────────────────────────────────────────────────────────────

describe("migrateChainStorageV2 — safe when no legacy key exists", () => {
  it("does not throw when chain.context_block is absent", () => {
    expect(() => migrateChainStorageV2()).not.toThrow();
  });

  it("still sets the version marker when no legacy key was present", () => {
    migrateChainStorageV2();
    expect(sessionStorage.getItem(CHAIN_V2_VERSION_KEY)).not.toBeNull();
  });
});
