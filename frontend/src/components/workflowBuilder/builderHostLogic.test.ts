import { beforeEach, describe, expect, it } from "vitest";

import type { TranscriptMessage } from "@/types/workflowBuilder";

import {
  clearNewConversationPending,
  isNewConversationPending,
  markNewConversationPending,
  recallPickerChoice,
  rememberPickerChoice,
  resetBuilderHandoff,
  stashFirstMessage,
  takeFirstMessage,
} from "./builderHandoff";
import {
  decideDraft,
  isBuilderRoute,
  linkedBaseIsCustom,
  manifestFingerprint,
  parseEditWorkflowId,
  retryTurnId,
  searchWithAi,
  sessionIdOf,
  sessionRoutePath,
} from "./builderHostLogic";

function assistant(seq: number, turnId: string, status: TranscriptMessage["status"]): TranscriptMessage {
  return {
    id: `m${seq}`,
    seq,
    role: "assistant",
    turn_id: turnId,
    reply_to_message_id: null,
    status,
    outcome: null,
    stop_reason: null,
    content: "",
    thinking: null,
    steps: null,
    model_id: "m",
    effort: null,
    skill_hash: null,
    skill_updated: false,
    error: null,
    revision: null,
    activity: [],
    activity_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    ended_at: null,
  };
}

describe("routes", () => {
  it("parseEditWorkflowId_returnsId_whenPathIsEditRoute", () => {
    expect(parseEditWorkflowId("/workflows/abc-123/edit")).toBe("abc-123");
    expect(parseEditWorkflowId("/workflows/abc-123/edit/")).toBe("abc-123");
  });

  it("parseEditWorkflowId_returnsNull_whenPathIsNotAnEditRoute", () => {
    expect(parseEditWorkflowId("/workflows/new")).toBeNull();
    expect(parseEditWorkflowId("/workflows/new/edit")).toBeNull();
    expect(parseEditWorkflowId("/workflows/abc/canvas")).toBeNull();
    expect(parseEditWorkflowId(null)).toBeNull();
  });

  it("isBuilderRoute_isTrueOnlyOnNewAndEdit_whenCheckingPaths", () => {
    expect(isBuilderRoute("/workflows/new")).toBe(true);
    expect(isBuilderRoute("/workflows/abc/edit")).toBe(true);
    expect(isBuilderRoute("/workflows")).toBe(false);
    expect(isBuilderRoute("/workflows/pptx/canvas")).toBe(false);
  });

  it("sessionRoutePath_returnsEditOrNewRoute_whenLinkedOrNot", () => {
    expect(sessionRoutePath("w1")).toBe("/workflows/w1/edit");
    expect(sessionRoutePath(null)).toBe("/workflows/new");
  });

  it("searchWithAi_setsAndRemovesAiAndKeepsOtherParams_whenCalled", () => {
    expect(searchWithAi("", "s1")).toBe("?ai=s1");
    expect(searchWithAi("?x=1", "s1")).toBe("?x=1&ai=s1");
    expect(searchWithAi("?x=1&ai=old", "s2")).toBe("?x=1&ai=s2");
    expect(searchWithAi("?ai=s1", null)).toBe("");
    expect(searchWithAi("?x=1&ai=s1", null)).toBe("?x=1");
  });
});

describe("sessionIdOf", () => {
  it("returnsTheSessionId_forEveryLoadKind", () => {
    expect(sessionIdOf({ kind: "none" })).toBeNull();
    expect(sessionIdOf({ kind: "loading", sessionId: "a" })).toBe("a");
    expect(sessionIdOf({ kind: "not_found", sessionId: "b" })).toBe("b");
  });
});

describe("decideDraft", () => {
  const base = { revision: 3, skipUpToRevision: 0, silent: false, dirty: false };

  it("decideDraft_applies_whenCanvasIsClean", () => {
    expect(decideDraft(base)).toBe("apply");
  });

  it("decideDraft_applies_whenThisTabAskedForItEvenIfDirty", () => {
    expect(decideDraft({ ...base, dirty: true, silent: true })).toBe("apply");
  });

  it("decideDraft_prompts_whenDirtyAndNotRequestedByThisTab", () => {
    expect(decideDraft({ ...base, dirty: true })).toBe("prompt");
  });

  it("decideDraft_skips_whenRevisionIsAtOrBelowTheLinkedRowCutoff", () => {
    expect(decideDraft({ ...base, skipUpToRevision: 3 })).toBe("skip");
    expect(decideDraft({ ...base, skipUpToRevision: 5, dirty: true, silent: true })).toBe("skip");
    expect(decideDraft({ ...base, skipUpToRevision: 2 })).toBe("apply");
  });
});

describe("retryTurnId", () => {
  it("retryTurnId_returnsTurnOfNewestAssistant_whenItFailed", () => {
    const messages = [assistant(2, "t1", "completed"), assistant(4, "t2", "failed")];
    expect(retryTurnId(messages)).toBe("t2");
  });

  it("retryTurnId_returnsNull_whenAnOlderTurnFailedButTheNewestDidNot", () => {
    const messages = [assistant(2, "t1", "failed"), assistant(4, "t2", "completed")];
    expect(retryTurnId(messages)).toBeNull();
    expect(retryTurnId([])).toBeNull();
  });
});

describe("manifestFingerprint", () => {
  it("manifestFingerprint_isEqual_whenOnlyDefaultsAndKeyOrderDiffer", () => {
    const a = { steps: [{ id: "s", agent: "writer" }], name: "x" };
    const b = { name: "x", steps: [{ agent: "writer", id: "s" }], description: null };
    expect(manifestFingerprint(a)).toBe(manifestFingerprint(b));
  });

  it("manifestFingerprint_differs_whenAStepChanges", () => {
    expect(manifestFingerprint({ steps: [{ id: "a" }] })).not.toBe(
      manifestFingerprint({ steps: [{ id: "b" }] }),
    );
  });
});

describe("linkedBaseIsCustom", () => {
  it("linkedBaseIsCustom_mapsBase_whenKnown", () => {
    expect(linkedBaseIsCustom("custom")).toBe(true);
    expect(linkedBaseIsCustom("prototype")).toBe(false);
    expect(linkedBaseIsCustom(null)).toBeUndefined();
    expect(linkedBaseIsCustom(undefined)).toBeUndefined();
  });
});

describe("builderHandoff", () => {
  beforeEach(() => resetBuilderHandoff());

  it("takeFirstMessage_returnsMessageOnce_whenStashed", () => {
    stashFirstMessage("s1", { text: "hi", modelId: "m", effort: null });
    expect(takeFirstMessage("s1")).toEqual({ text: "hi", modelId: "m", effort: null });
    expect(takeFirstMessage("s1")).toBeNull();
    expect(takeFirstMessage("other")).toBeNull();
  });

  it("recallPickerChoice_returnsLastChoice_whenRemembered", () => {
    expect(recallPickerChoice()).toBeNull();
    rememberPickerChoice({ modelId: "m", effort: "high" });
    expect(recallPickerChoice()).toEqual({ modelId: "m", effort: "high" });
  });

  it("isNewConversationPending_staysTrueUntilCleared_whenMarked", () => {
    markNewConversationPending();
    expect(isNewConversationPending()).toBe(true);
    expect(isNewConversationPending()).toBe(true);
    clearNewConversationPending();
    expect(isNewConversationPending()).toBe(false);
  });
});
