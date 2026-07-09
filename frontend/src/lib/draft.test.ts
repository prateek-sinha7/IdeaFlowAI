/**
 * ND-1 (LOCK-E) — the Configure run-draft is CLIENT-SIDE ONLY. `draft.ts` keeps
 * ONE keyed JSON blob in sessionStorage (`configure.draft`), a peer of
 * `prototype.draft` — NOT of the `chain.*` run-chaining keys. It has NO DB, NO
 * migration, NO fetch/api seam: the blob is written on Save-draft, read on
 * mount, and cleared once at launch.
 *
 * These tests pin the round-trip + the fail-soft contract:
 *   - save → read returns the same superset-of-LaunchCommand payload;
 *   - clear removes it (read → null);
 *   - a malformed blob returns null (never throws) — a corrupt tab-store must not
 *     crash the Configure screen.
 */

import { describe, expect, it, beforeEach } from "vitest";
import { saveDraft, readDraft, clearDraft, type ConfigureDraft } from "./draft";

const KEY = "configure.draft";

describe("draft.ts — client-side sessionStorage run-draft (ND-1)", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("round-trips the full ConfigureDraft superset (save → read)", () => {
    const payload: ConfigureDraft = {
      templateId: "kanban",
      designSystemId: "midnight",
      brief: "A kanban board for a 5-person squad",
      agentIds: ["a1", "a2"],
      selections: { a1: { validators: ["render_check"], gates: ["validation"] } },
      modelOverrides: { a1: "claude-sonnet" },
      customDsBody: null,
      customTemplateBody: null,
      gateAgentIds: ["a2"],
      discovery: { surface: "Desktop web" },
    };

    saveDraft(payload);

    // The blob lives under the distinct `configure.draft` key (peer of prototype.draft).
    expect(sessionStorage.getItem(KEY)).not.toBeNull();
    expect(readDraft()).toEqual(payload);
  });

  it("returns null when no draft has been written", () => {
    expect(readDraft()).toBeNull();
  });

  it("clearDraft removes the blob — reading after clear returns null", () => {
    saveDraft({ brief: "x" });
    expect(readDraft()).not.toBeNull();

    clearDraft();

    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(readDraft()).toBeNull();
  });

  it("returns null (never throws) on a malformed blob", () => {
    sessionStorage.setItem(KEY, "{not valid json");
    expect(() => readDraft()).not.toThrow();
    expect(readDraft()).toBeNull();
  });

  it("overwrites the previous draft (single keyed blob, not append)", () => {
    saveDraft({ brief: "first" });
    saveDraft({ brief: "second" });
    expect(readDraft()).toEqual({ brief: "second" });
  });
});
