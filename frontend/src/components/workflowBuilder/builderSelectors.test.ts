import { describe, expect, it } from "vitest";

import { INITIAL_BUILDER_STATE, type BuilderState, type TurnView } from "./builderReducer";
import {
  MAX_MESSAGE_CODE_POINTS,
  activitySummary,
  canSend,
  codePointLength,
  formatElapsed,
  isTurnRunning,
  orderedStepsOf,
  storedStepsToTurnSteps,
  undoTargetMessageId,
} from "./builderSelectors";
import type { CheckResult, ToolActivity } from "@/types/workflowBuilder";

const IDLE: TurnView = { kind: "idle" };
const SENDING: TurnView = { kind: "sending", clientMessageId: "c1", text: "hi" };
const RUNNING: TurnView = {
  kind: "running",
  turnId: "t1",
  origin: "other_tab",
  stage: "starting",
  label: "Starting",
  startedAt: 0,
  lastSeq: 1,
  activity: [],
  steps: [],
  warnings: [],
  pendingDraft: null,
};
const ENDED: TurnView = {
  kind: "ended",
  turnId: "t1",
  status: "completed",
  outcome: "reply",
  stopReason: null,
};

describe("storedStepsToTurnSteps", () => {
  const check: CheckResult = {
    source: "skill_validator", verdict: "valid", errors: 0, warnings: 0,
    attempt: null, attempts_left: null,
  };

  it("returns null for null, for a missing key and for an empty list", () => {
    expect(storedStepsToTurnSteps(null)).toBeNull();
    expect(storedStepsToTurnSteps(undefined as unknown as null)).toBeNull();
    expect(storedStepsToTurnSteps([])).toBeNull();
  });

  it("keeps the order and maps each kind to the live step shape", () => {
    expect(
      storedStepsToTurnSteps([
        { kind: "thinking", text: "t" },
        { kind: "tools", call_ids: ["c1", "c2"] },
        { kind: "check", check },
      ]),
    ).toEqual([
      { kind: "thinking", id: "stored-0", text: "t" },
      { kind: "tools", id: "stored-1", callIds: ["c1", "c2"] },
      { kind: "check", id: "stored-2", check },
    ]);
  });
});

describe("orderedStepsOf", () => {
  const steps = [{ kind: "thinking" as const, text: "t" }];
  const summary = { actions: 2, checks: 0, duration_ms: 10 };

  it("returns the steps for an assistant message that made tool calls", () => {
    expect(orderedStepsOf({ role: "assistant", steps, activity_summary: summary })).toEqual([
      { kind: "thinking", id: "stored-0", text: "t" },
    ]);
  });

  it("returns null for a user message", () => {
    expect(orderedStepsOf({ role: "user", steps, activity_summary: summary })).toBeNull();
  });

  it("returns null when the turn made no tool calls, so the Thinking block stays", () => {
    expect(
      orderedStepsOf({ role: "assistant", steps, activity_summary: { ...summary, actions: 0 } }),
    ).toBeNull();
    expect(orderedStepsOf({ role: "assistant", steps, activity_summary: null })).toBeNull();
  });

  it("returns null when no steps were stored", () => {
    expect(orderedStepsOf({ role: "assistant", steps: null, activity_summary: summary })).toBeNull();
  });
});

describe("codePointLength", () => {
  it("counts an astral character once", () => {
    expect("😀".length).toBe(2);
    expect(codePointLength("😀a")).toBe(2);
  });
});

describe("canSend", () => {
  it("allows plain text when idle or ended", () => {
    expect(canSend("hello", IDLE)).toBe(true);
    expect(canSend("hello", ENDED)).toBe(true);
  });

  it("refuses while a turn is sending or running", () => {
    expect(canSend("hello", SENDING)).toBe(false);
    expect(canSend("hello", RUNNING)).toBe(false);
  });

  it("refuses empty and whitespace-only text, using Python's whitespace set", () => {
    expect(canSend("", IDLE)).toBe(false);
    expect(canSend(" \n\t ", IDLE)).toBe(false);
    expect(canSend("\u0085\u001f", IDLE)).toBe(false);
    // U+FEFF is not whitespace to Python's strip(), so the server accepts it.
    expect(canSend("\uFEFF", IDLE)).toBe(true);
  });

  it("counts code points against the limit", () => {
    expect(canSend("😀".repeat(MAX_MESSAGE_CODE_POINTS), IDLE)).toBe(true);
    expect(canSend("😀".repeat(MAX_MESSAGE_CODE_POINTS + 1), IDLE)).toBe(false);
  });
});

describe("undoTargetMessageId", () => {
  const transcript = [
    { id: "u1", seq: 1, role: "user", revision: null },
    { id: "a1", seq: 2, role: "assistant", revision: 1 },
    { id: "u2", seq: 3, role: "user", revision: null },
    { id: "a2", seq: 4, role: "assistant", revision: 2 },
    { id: "a3", seq: 6, role: "assistant", revision: null },
  ] as const;

  it("picks the assistant message that holds the latest accepted revision", () => {
    const revisions = [
      { revision: 1, kind: "accepted" },
      { revision: 2, kind: "accepted" },
    ] as const;
    expect(undoTargetMessageId(transcript, revisions)).toBe("a2");
  });

  it("offers nothing when the latest revision is not accepted", () => {
    const revisions = [
      { revision: 2, kind: "accepted" },
      { revision: 3, kind: "undo" },
    ] as const;
    expect(undoTargetMessageId(transcript, revisions)).toBeNull();
  });

  it("offers nothing without revisions or without a matching message", () => {
    expect(undoTargetMessageId(transcript, [])).toBeNull();
    expect(undoTargetMessageId(transcript, [{ revision: 9, kind: "accepted" }])).toBeNull();
  });
});

describe("formatElapsed", () => {
  it("formats seconds and minutes", () => {
    expect(formatElapsed(40_900)).toBe("40 s");
    expect(formatElapsed(100_000)).toBe("1 min 40 s");
    expect(formatElapsed(120_000)).toBe("2 min");
    expect(formatElapsed(-5)).toBe("0 s");
    expect(formatElapsed(Number.NaN)).toBe("0 s");
  });
});

describe("activitySummary", () => {
  const line = (id: string): ToolActivity => ({
    call_id: id,
    tool: "read_file",
    kind: "read",
    label: "Read",
    status: "ok",
    duration_ms: 1,
    command: null,
    exit_code: null,
    summary: null,
  });
  const check: CheckResult = {
    source: "skill_validator",
    verdict: "valid",
    errors: 0,
    warnings: 0,
    attempt: null,
    attempts_left: null,
  };

  it("joins counts and duration", () => {
    const activity = Array.from({ length: 14 }, (_, i) => line(`c${i}`));
    expect(activitySummary(activity, [check, check], 100_000)).toBe(
      "14 actions, 2 checks, 1 min 40 s",
    );
  });

  it("uses singular nouns for one", () => {
    expect(activitySummary([line("c1")], [check], 5_000)).toBe("1 action, 1 check, 5 s");
  });
});

describe("isTurnRunning", () => {
  const withTurn = (turn: TurnView): BuilderState => ({ ...INITIAL_BUILDER_STATE, turn });

  it("is true only while a turn is running", () => {
    expect(isTurnRunning(withTurn(RUNNING))).toBe(true);
    expect(isTurnRunning(withTurn(IDLE))).toBe(false);
    expect(isTurnRunning(withTurn(SENDING))).toBe(false);
    expect(isTurnRunning(withTurn(ENDED))).toBe(false);
  });
});
