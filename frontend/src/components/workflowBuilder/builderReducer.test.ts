import { describe, expect, it } from "vitest";

import type { BuilderEvent, SessionDetail } from "@/types/workflowBuilder";

import {
  builderReducer,
  INITIAL_BUILDER_STATE,
  type BuilderAction,
  type BuilderState,
} from "./builderReducer";

const TS = "2026-01-01T00:00:00Z";
const MANIFEST = { steps: [{ id: "a" }] };

function run(actions: BuilderAction[], from: BuilderState = INITIAL_BUILDER_STATE): BuilderState {
  return actions.reduce(builderReducer, from);
}

function ev(event: BuilderEvent): BuilderAction {
  return { type: "stream_event", event, now: 1000 };
}

const started = (turn_id: string, seq = 1): BuilderEvent => ({
  type: "turn_started", ts: TS, turn_id, seq, message_id: "m1", model_id: "x", effort: null, skill_hash: "h",
});
const text = (turn_id: string, seq: number, t: string): BuilderEvent => ({
  type: "text", ts: TS, turn_id, seq, text: t,
});
const applied = (turn_id: string, seq: number, revision: number): BuilderEvent => ({
  type: "draft_applied", ts: TS, turn_id, seq, revision, target_trust: "user",
  change_summary: {
    added: [], removed: [], reordered: false, gates_changed: [],
    validators_changed: [], models_changed: [], prompts_changed: 0,
  },
  launch_needs: [], manifest: MANIFEST,
});
const completed = (turn_id: string, seq: number): BuilderEvent => ({
  type: "turn_completed", ts: TS, turn_id, seq, status: "completed", outcome: "draft",
  stop_reason: null, message_id: "m2", revision: 1,
  usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, summary: null },
});

describe("builderReducer", () => {
  it("appends text only for this_tab turns", () => {
    const own = run([
      { type: "send_started", clientMessageId: "c1", text: "hi" },
      ev(started("t1")),
      ev(text("t1", 2, "ab")),
      ev(text("t1", 3, "cd")),
    ]);
    expect(own.turn).toMatchObject({
      kind: "running",
      origin: "this_tab",
      steps: [{ kind: "text", text: "abcd" }],
    });

    const other = run([ev(started("t2")), ev(text("t2", 2, "ab"))]);
    expect(other.turn).toMatchObject({ kind: "running", origin: "other_tab", steps: [] });
  });

  it("ignores turn events at or below lastSeq", () => {
    const state = run([
      { type: "send_started", clientMessageId: "c1", text: "hi" },
      ev(started("t1")),
      ev(text("t1", 2, "a")),
      ev(text("t1", 2, "dup")),
      ev(text("t1", 1, "old")),
    ]);
    expect(state.turn).toMatchObject({ lastSeq: 2, steps: [{ kind: "text", text: "a" }] });
  });

  it("applies draft_applied at once in the sending tab", () => {
    const state = run([
      { type: "send_started", clientMessageId: "c1", text: "hi" },
      ev(started("t1")),
      ev(applied("t1", 2, 3)),
    ]);
    expect(state.draft).toMatchObject({ kind: "applied", revision: 3 });
  });

  it("holds draft_applied in pendingDraft elsewhere until turn_completed", () => {
    const mid = run([ev(started("t2")), ev(applied("t2", 2, 4))]);
    expect(mid.draft.kind).toBe("none");
    expect(mid.turn).toMatchObject({ kind: "running" });

    const done = builderReducer(mid, ev(completed("t2", 3)));
    expect(done.draft).toMatchObject({ kind: "applied", revision: 4 });
    expect(done.turn).toMatchObject({ kind: "ended", turnId: "t2", status: "completed" });
    expect(done.needsReload).toBe(true);
  });

  it("applies draft_restored and ignores an older revision", () => {
    const state = run([
      ev({ type: "draft_restored", ts: TS, revision: 5, manifest: MANIFEST }),
      ev({ type: "draft_restored", ts: TS, revision: 2, manifest: { steps: [] } }),
    ]);
    expect(state.draft).toMatchObject({ kind: "applied", revision: 5 });
  });

  it("builds a rejoined turn from a snapshot", () => {
    const state = run([
      ev({
        type: "snapshot", ts: TS, state: "running", latest_message_id: null,
        latest_revision: null, latest_unproposed_revision: null,
        running_turn: {
          turn_id: "t9", message_id: "m9", stage: "reading", label: "Reading",
          started_at: TS, through_seq: 7, activity: [], checks: [],
        },
      }),
      ev(text("t9", 8, "mid-sentence")),
    ]);
    expect(state.turn).toMatchObject({ kind: "running", origin: "rejoined", lastSeq: 8, steps: [] });
  });

  it("returns a 409 conflict to idle with a notice", () => {
    const state = run([
      { type: "send_started", clientMessageId: "c1", text: "hi" },
      { type: "send_failed", reason: "conflict" },
    ]);
    expect(state.turn.kind).toBe("idle");
    expect(state.notice.kind).toBe("reply_in_progress_elsewhere");
  });

  it("keeps the session loaded from the REST call and skips a seed draft", () => {
    const session = {
      id: "s1", linked_row_changed: true, target_trust: "user", messages: [],
      latest_draft: { revision: 1, kind: "seed", manifest: MANIFEST },
    } as unknown as SessionDetail;
    const state = run([
      { type: "session_loading", sessionId: "s1" },
      { type: "session_loaded", session },
    ]);
    expect(state.load.kind).toBe("ready");
    expect(state.draft.kind).toBe("none");
    expect(state.notice.kind).toBe("linked_row_changed");
  });
});

// --- Named transitions (task 18.17) --------------------------------------------------

const stage = (turn_id: string, seq: number): BuilderEvent => ({
  type: "stage", ts: TS, turn_id, seq, stage: "checking", label: "Checking",
});
const toolStarted = (turn_id: string, seq: number, call_id: string): BuilderEvent => ({
  type: "tool_started", ts: TS, turn_id, seq, call_id, tool: "read_file", kind: "read",
  label: "Read a file", command: null,
});
const toolFinished = (turn_id: string, seq: number, call_id: string): BuilderEvent => ({
  type: "tool_finished", ts: TS, turn_id, seq, call_id, status: "ok", duration_ms: 12,
  summary: "Read a file.",
});
const check = (turn_id: string, seq: number): BuilderEvent => ({
  type: "check_result", ts: TS, turn_id, seq, source: "skill_validator", verdict: "invalid",
  errors: 2, warnings: 0, attempt: 1, attempts_left: 1,
});
const limit = (turn_id: string, seq: number, used: number): BuilderEvent => ({
  type: "limit_warning", ts: TS, turn_id, seq, kind: "tool_calls", used, limit: 60,
});
const snapshot = (
  overrides: Partial<Extract<BuilderEvent, { type: "snapshot" }>> = {},
): BuilderEvent => ({
  type: "snapshot", ts: TS, state: "idle", running_turn: null, latest_message_id: null,
  latest_revision: null, latest_unproposed_revision: null, ...overrides,
});
const runningSnapshot = (turn_id: string, through_seq: number) => ({
  turn_id, message_id: "m", stage: "reading" as const, label: "Reading", started_at: TS,
  through_seq, activity: [], checks: [],
});

function session(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: "s1", title: "t", mode: "create", workflow_id: null, model_id: "x", effort: null,
    running: false, created_at: TS, updated_at: TS, target_trust: "user", skill_hash: "h",
    messages: [], latest_draft: null, latest_unproposed: null, running_turn: null,
    linked_row_changed: false, ...overrides,
  };
}

const sending = (): BuilderAction => ({ type: "send_started", clientMessageId: "c1", text: "hi" });

describe("builderReducer session transitions", () => {
  it("session_loading resets everything but keeps the panel open flag", () => {
    const state = run([
      { type: "panel_set", open: true },
      ev(started("t1")),
      { type: "session_loading", sessionId: "s2" },
    ]);
    expect(state).toEqual({
      ...INITIAL_BUILDER_STATE,
      load: { kind: "loading", sessionId: "s2" },
      panelOpen: true,
    });
  });

  it("session_not_found marks the load and session_cleared returns to the initial state", () => {
    const missing = run([{ type: "session_not_found", sessionId: "s1" }]);
    expect(missing.load).toEqual({ kind: "not_found", sessionId: "s1" });

    const cleared = builderReducer(
      { ...missing, panelOpen: true },
      { type: "session_cleared" },
    );
    expect(cleared).toEqual({ ...INITIAL_BUILDER_STATE, panelOpen: true });
  });

  it("session_loaded clears needsReload and ignores a different session id", () => {
    const loaded = run([
      { type: "session_loading", sessionId: "s1" },
      ev(started("t1")),
      ev(completed("t1", 2)),
    ]);
    expect(loaded.needsReload).toBe(true);

    const ready = builderReducer(loaded, { type: "session_loaded", session: session() });
    expect(ready.load.kind).toBe("ready");
    expect(ready.needsReload).toBe(false);

    const other = builderReducer(ready, { type: "session_loaded", session: session({ id: "s9" }) });
    expect(other).toBe(ready);
  });

  it("session_loaded applies an accepted draft and keeps the first notice", () => {
    const state = run([
      { type: "notice_set", notice: { kind: "model_unavailable", fallbackModelId: "y" } },
      {
        type: "session_loaded",
        session: session({
          linked_row_changed: true,
          latest_draft: {
            revision: 4, kind: "accepted", manifest: MANIFEST, target_trust: "db",
            change_summary: null, launch_needs: [], source_turn_id: "t1", created_at: TS,
          },
        }),
      },
    ]);
    expect(state.draft).toMatchObject({ kind: "applied", revision: 4, targetTrust: "db" });
    expect(state.notice.kind).toBe("model_unavailable");
  });

  it("reload_acknowledged clears needsReload without a load", () => {
    const state = run([ev(started("t1")), ev(completed("t1", 2)), { type: "reload_acknowledged" }]);
    expect(state.needsReload).toBe(false);
  });
});

describe("builderReducer send transitions", () => {
  it("send_started moves to sending and clears the elsewhere notice", () => {
    const state = run([
      { type: "notice_set", notice: { kind: "reply_in_progress_elsewhere" } },
      sending(),
    ]);
    expect(state.turn).toEqual({ kind: "sending", clientMessageId: "c1", text: "hi" });
    expect(state.notice.kind).toBe("none");
  });

  it("send_started is ignored while a turn is sending or running", () => {
    const busy = run([sending()]);
    expect(builderReducer(busy, { type: "send_started", clientMessageId: "c2", text: "x" })).toBe(busy);

    const running = run([ev(started("t1"))]);
    expect(builderReducer(running, sending())).toBe(running);
  });

  it("send_accepted records own turn ids once, newest last, capped at 20", () => {
    const ids = Array.from({ length: 22 }, (_, i) => `t${i}`);
    const state = run([
      ...ids.map((turnId): BuilderAction => ({ type: "send_accepted", turnId })),
      { type: "send_accepted", turnId: "t10" },
    ]);
    expect(state.ownTurnIds).toHaveLength(20);
    expect(state.ownTurnIds[state.ownTurnIds.length - 1]).toBe("t10");
    expect(state.ownTurnIds.filter((id) => id === "t10")).toHaveLength(1);
    expect(state.ownTurnIds).not.toContain("t0");
  });

  it("a turn whose id the send call returned is this_tab even when idle", () => {
    const state = run([{ type: "send_accepted", turnId: "t1" }, ev(started("t1"))]);
    expect(state.turn).toMatchObject({ kind: "running", origin: "this_tab" });
  });

  it("send_failed(other) returns a sending turn to idle and leaves other turns alone", () => {
    expect(run([sending(), { type: "send_failed", reason: "other" }]).turn.kind).toBe("idle");

    const running = run([ev(started("t1"))]);
    expect(builderReducer(running, { type: "send_failed", reason: "other" })).toBe(running);
  });

  it("send_failed(conflict) downgrades a turn that only looked like ours", () => {
    const state = run([
      sending(),
      ev(started("t7")),
      ev(text("t7", 2, "not ours")),
      { type: "send_failed", reason: "conflict" },
    ]);
    expect(state.turn).toMatchObject({ kind: "running", origin: "other_tab", steps: [] });
    expect(state.notice.kind).toBe("reply_in_progress_elsewhere");
  });

  it("send_failed(conflict) keeps a turn the send call confirmed as ours", () => {
    const state = run([
      sending(),
      { type: "send_accepted", turnId: "t7" },
      ev(started("t7")),
      ev(text("t7", 2, "ours")),
      { type: "send_failed", reason: "conflict" },
    ]);
    expect(state.turn).toMatchObject({ origin: "this_tab", steps: [{ kind: "text", text: "ours" }] });
  });
});

describe("builderReducer pending user message", () => {
  const userRow = (turn_id: string) =>
    ({ role: "user", turn_id }) as SessionDetail["messages"][number];

  it("keeps the sent text through turn_started and turn_completed", () => {
    const state = run([
      sending(),
      { type: "send_accepted", turnId: "t1" },
      ev(started("t1")),
      ev(text("t1", 2, "reply")),
      ev(completed("t1", 3)),
    ]);
    expect(state.pendingUser).toEqual({ text: "hi", turnId: "t1" });
  });

  it("clears the sent text once a loaded session holds its user row", () => {
    const before = run([sending(), { type: "send_accepted", turnId: "t1" }, ev(started("t1"))]);
    const unrelated = builderReducer(before, {
      type: "session_loaded",
      session: session({ messages: [userRow("t0")] }),
    });
    expect(unrelated.pendingUser).not.toBeNull();

    const stored = builderReducer(unrelated, {
      type: "session_loaded",
      session: session({ messages: [userRow("t0"), userRow("t1")] }),
    });
    expect(stored.pendingUser).toBeNull();
  });

  it("keeps the sent text when a session loads before the send call returns", () => {
    const state = run([
      sending(),
      { type: "session_loaded", session: session({ messages: [userRow("t1")] }) },
    ]);
    expect(state.pendingUser).toEqual({ text: "hi", turnId: null });
  });

  it.each(["conflict", "other"] as const)("clears the sent text when the send fails (%s)", (reason) => {
    const state = run([sending(), { type: "send_failed", reason }]);
    expect(state.pendingUser).toBeNull();
  });

  it("a retry with no text leaves no pending message", () => {
    const state = run([{ type: "send_started", clientMessageId: "c2", text: "" }]);
    expect(state.pendingUser).toBeNull();
  });
});

describe("builderReducer turn events", () => {
  it("turn_started starts at the starting stage with the event seq", () => {
    const state = run([ev({ ...started("t1", 5) })]);
    expect(state.turn).toMatchObject({
      kind: "running", turnId: "t1", stage: "starting", lastSeq: 5, startedAt: 1000,
    });
  });

  it("a repeated turn_started for the running turn only advances lastSeq", () => {
    const first = run([ev(started("t1", 1)), ev(text("t1", 2, "a"))]);
    const again = builderReducer(first, ev(started("t1", 1)));
    expect(again).toBe(first);
  });

  it("a different turn_started while running replaces the turn and asks for a reload", () => {
    const state = run([ev(started("t1")), ev(started("t2"))]);
    expect(state.turn).toMatchObject({ kind: "running", turnId: "t2" });
    expect(state.needsReload).toBe(true);
  });

  it("stage updates the stage and label", () => {
    const state = run([ev(started("t1")), ev(stage("t1", 2))]);
    expect(state.turn).toMatchObject({ stage: "checking", label: "Checking", lastSeq: 2 });
  });

  it("events for another turn are ignored", () => {
    const base = run([ev(started("t1"))]);
    expect(builderReducer(base, ev(stage("t9", 2)))).toBe(base);
  });

  it("thinking is kept only for this_tab", () => {
    const thinking = (turn_id: string): BuilderEvent => ({
      type: "thinking", ts: TS, turn_id, seq: 2, text: "hm",
    });
    expect(run([sending(), ev(started("t1")), ev(thinking("t1"))]).turn).toMatchObject({
      steps: [{ kind: "thinking", text: "hm" }],
    });
    expect(run([ev(started("t2")), ev(thinking("t2"))]).turn).toMatchObject({ steps: [] });
  });

  it("tool_started adds one running line, tool_finished completes it", () => {
    const mid = run([ev(started("t1")), ev(toolStarted("t1", 2, "c1"))]);
    expect(mid.turn).toMatchObject({
      activity: [{ call_id: "c1", status: "running", duration_ms: null, summary: null }],
    });

    const done = builderReducer(mid, ev(toolFinished("t1", 3, "c1")));
    expect(done.turn).toMatchObject({
      activity: [{ call_id: "c1", status: "ok", duration_ms: 12, summary: "Read a file." }],
    });
  });

  it("a repeated tool_started and a tool_finished for an unknown call change nothing visible", () => {
    const state = run([
      ev(started("t1")),
      ev(toolStarted("t1", 2, "c1")),
      ev(toolStarted("t1", 3, "c1")),
      ev(toolFinished("t1", 4, "unknown")),
    ]);
    expect(state.turn).toMatchObject({
      lastSeq: 4,
      activity: [{ call_id: "c1", status: "running" }],
    });
  });

  it("check_result appends a check line", () => {
    const state = run([ev(started("t1")), ev(check("t1", 2))]);
    expect(state.turn).toMatchObject({
      steps: [
        {
          kind: "check",
          check: { source: "skill_validator", verdict: "invalid", errors: 2, attempts_left: 1 },
        },
      ],
    });
  });

  it("limit_warning keeps one warning per kind, the latest", () => {
    const state = run([ev(started("t1")), ev(limit("t1", 2, 48)), ev(limit("t1", 3, 55))]);
    expect(state.turn).toMatchObject({ warnings: [{ kind: "tool_calls", used: 55, limit: 60 }] });
  });

  it("turn_completed ends the turn, asks for a reload and clears the elsewhere notice", () => {
    const state = run([
      { type: "notice_set", notice: { kind: "reply_in_progress_elsewhere" } },
      ev(started("t1")),
      ev({ ...completed("t1", 2), status: "timed_out", stop_reason: "time", outcome: "unfinished" } as BuilderEvent),
    ]);
    expect(state.turn).toEqual({
      kind: "ended", turnId: "t1", status: "timed_out", outcome: "unfinished", stopReason: "time",
    });
    expect(state.needsReload).toBe(true);
    expect(state.notice.kind).toBe("none");
  });
});

describe("builderReducer ordered steps", () => {
  const thinking = (turn_id: string, seq: number, t: string): BuilderEvent => ({
    type: "thinking", ts: TS, turn_id, seq, text: t,
  });
  const kinds = (state: BuilderState) =>
    state.turn.kind === "running" ? state.turn.steps.map((s) => s.kind) : [];

  it("keeps thinking, tool calls, a check and text in arrival order", () => {
    const state = run([
      sending(),
      ev(started("t1")),
      ev(thinking("t1", 2, "one")),
      ev(toolStarted("t1", 3, "c1")),
      ev(toolFinished("t1", 4, "c1")),
      ev(thinking("t1", 5, "two")),
      ev(toolStarted("t1", 6, "c2")),
      ev(check("t1", 7)),
      ev(text("t1", 8, "answer")),
    ]);
    expect(kinds(state)).toEqual(["thinking", "tools", "thinking", "tools", "check", "text"]);
  });

  it("joins deltas of one kind and calls with no step between them", () => {
    const state = run([
      sending(),
      ev(started("t1")),
      ev(thinking("t1", 2, "a")),
      ev(thinking("t1", 3, "b")),
      ev(toolStarted("t1", 4, "c1")),
      ev(toolStarted("t1", 5, "c2")),
    ]);
    expect(state.turn).toMatchObject({
      steps: [
        { kind: "thinking", text: "ab" },
        { kind: "tools", callIds: ["c1", "c2"] },
      ],
    });
  });

  it("keeps tool calls and checks in a watching tab but drops thinking and text", () => {
    const state = run([
      ev(started("t2")),
      ev(thinking("t2", 2, "hidden")),
      ev(toolStarted("t2", 3, "c1")),
      ev(text("t2", 4, "hidden")),
      ev(check("t2", 5)),
    ]);
    expect(kinds(state)).toEqual(["tools", "check"]);
  });

  it("adds calls and checks a snapshot reports and keeps this tab's thinking", () => {
    const withSnapshot = run([
      sending(),
      ev(started("t1")),
      ev(thinking("t1", 2, "kept")),
      ev(
        snapshot({
          state: "running",
          running_turn: {
            ...runningSnapshot("t1", 5),
            activity: [
              {
                call_id: "c9", tool: "read_file", kind: "read", label: "Read", status: "ok",
                duration_ms: 3, command: null, exit_code: null, summary: null,
              },
            ],
          },
        }),
      ),
    ]);
    expect(kinds(withSnapshot)).toEqual(["thinking", "tools"]);
  });

  it("builds tool steps from the snapshot of a rejoined turn", () => {
    const state = run([
      ev(
        snapshot({
          state: "running",
          running_turn: {
            ...runningSnapshot("t9", 4),
            activity: [
              {
                call_id: "c1", tool: "read_file", kind: "read", label: "Read", status: "ok",
                duration_ms: 3, command: null, exit_code: null, summary: null,
              },
            ],
            checks: [
              { source: "skill_validator", verdict: "valid", errors: 0, warnings: 0, attempt: null, attempts_left: null },
            ],
          },
        }),
      ),
    ]);
    expect(kinds(state)).toEqual(["tools", "check"]);
  });
});

describe("builderReducer drafts", () => {
  it("ignores a draft with no steps array", () => {
    const state = run([
      sending(),
      ev(started("t1")),
      ev({ ...applied("t1", 2, 3), manifest: { name: "x" } } as BuilderEvent),
    ]);
    expect(state.draft.kind).toBe("none");
  });

  it("ignores a draft that is not newer than the canvas", () => {
    const base = run([sending(), ev(started("t1")), ev(applied("t1", 2, 3))]);
    const same = builderReducer(base, ev(applied("t1", 3, 3)));
    expect(same.draft).toBe(base.draft);
  });

  it("draft_applied updates the cached session's latest draft", () => {
    const state = run([
      { type: "session_loaded", session: session({ latest_unproposed: null }) },
      sending(),
      ev(started("t1")),
      ev(applied("t1", 2, 3)),
    ]);
    expect(state.load.kind === "ready" && state.load.session.latest_draft).toMatchObject({
      revision: 3, kind: "accepted", source_turn_id: "t1",
    });
  });

  it("draft_restored takes the current draft's trust and records an undo revision", () => {
    const state = run([
      { type: "session_loaded", session: session({ target_trust: "db" }) },
      ev({ type: "draft_restored", ts: TS, revision: 2, manifest: MANIFEST }),
    ]);
    expect(state.draft).toMatchObject({ revision: 2, targetTrust: "db" });
    expect(state.load.kind === "ready" && state.load.session.latest_draft).toMatchObject({
      kind: "undo", revision: 2,
    });
  });

  it("draft fingerprint is equal for equal manifests and differs for different ones", () => {
    const a = run([ev({ type: "draft_restored", ts: TS, revision: 1, manifest: { steps: [{ id: "a" }] } })]);
    const b = run([ev({ type: "draft_restored", ts: TS, revision: 1, manifest: { steps: [{ id: "a" }] } })]);
    const c = run([ev({ type: "draft_restored", ts: TS, revision: 1, manifest: { steps: [{ id: "b" }] } })]);
    const fingerprint = (s: BuilderState) => (s.draft.kind === "applied" ? s.draft.fingerprint : null);
    expect(fingerprint(a)).toBe(fingerprint(b));
    expect(fingerprint(a)).not.toBe(fingerprint(c));
  });
});

describe("builderReducer snapshots", () => {
  it("keeps text and origin when the snapshot shows the same running turn", () => {
    const state = run([
      sending(),
      ev(started("t1")),
      ev(text("t1", 2, "abc")),
      ev(snapshot({ state: "running", running_turn: runningSnapshot("t1", 1) })),
    ]);
    expect(state.turn).toMatchObject({
      origin: "this_tab",
      steps: [{ kind: "text", text: "abc" }],
      lastSeq: 2,
      stage: "reading",
    });
  });

  it("raises lastSeq to through_seq so covered events are not applied twice", () => {
    const state = run([
      ev(started("t1")),
      ev(snapshot({ state: "running", running_turn: runningSnapshot("t1", 9) })),
      ev(stage("t1", 9)),
    ]);
    expect(state.turn).toMatchObject({ lastSeq: 9, stage: "reading" });
  });

  it("measures a rejoined turn's age on the server clock", () => {
    const state = builderReducer(INITIAL_BUILDER_STATE, {
      type: "stream_event",
      now: 100_000,
      event: snapshot({
        ts: "2026-01-01T00:00:10Z",
        state: "running",
        running_turn: runningSnapshot("t1", 3),
      }),
    });
    expect(state.turn).toMatchObject({ origin: "rejoined", startedAt: 90_000 });
  });

  it("an idle snapshot ends a running turn and asks for a reload", () => {
    const state = run([ev(started("t1")), ev(snapshot())]);
    expect(state.turn.kind).toBe("idle");
    expect(state.needsReload).toBe(true);
  });

  it("an idle snapshot with no running turn changes nothing", () => {
    const state = run([ev(snapshot())]);
    expect(state).toEqual(INITIAL_BUILDER_STATE);
  });

  it("a newer latest_revision than the canvas asks for a reload once a session is loaded", () => {
    const loaded = run([{ type: "session_loaded", session: session() }]);
    expect(builderReducer(loaded, ev(snapshot({ latest_revision: 3 }))).needsReload).toBe(true);
    expect(builderReducer(INITIAL_BUILDER_STATE, ev(snapshot({ latest_revision: 3 }))).needsReload).toBe(false);
  });
});

describe("builderReducer other stream events", () => {
  it("session_deleted marks the session gone and ends the turn", () => {
    const state = run([
      { type: "session_loaded", session: session() },
      ev(started("t1")),
      ev({ type: "session_deleted", ts: TS }),
    ]);
    expect(state.load).toEqual({ kind: "not_found", sessionId: "s1" });
    expect(state.turn.kind).toBe("idle");
    expect(state.notice.kind).toBe("deleted_elsewhere");
  });

  it("session_revoked changes nothing", () => {
    const base = run([ev(started("t1"))]);
    const state = builderReducer(
      base,
      ev({ type: "session_revoked", ts: TS, session_id: "s1", reason: "logout" }),
    );
    expect(state).toBe(base);
  });

  it("error with a turn only advances lastSeq, and a turnless error changes nothing", () => {
    const base = run([ev(started("t1"))]);
    const withTurn = builderReducer(
      base,
      ev({ type: "error", ts: TS, turn_id: "t1", seq: 2, code: "x", message: "m", retryable: true }),
    );
    expect(withTurn.turn).toMatchObject({ lastSeq: 2 });
    expect(withTurn.draft).toBe(base.draft);

    const turnless = builderReducer(
      base,
      ev({ type: "error", ts: TS, turn_id: null, seq: null, code: "x", message: "m", retryable: false }),
    );
    expect(turnless).toBe(base);
  });
});

describe("builderReducer panel and notices", () => {
  it("notice_set replaces the notice and notice_dismissed clears it", () => {
    const set = run([{ type: "notice_set", notice: { kind: "deleted_elsewhere" } }]);
    expect(set.notice.kind).toBe("deleted_elsewhere");
    expect(builderReducer(set, { type: "notice_dismissed" }).notice.kind).toBe("none");
  });

  it("panel_set opens and closes the panel", () => {
    const open = run([{ type: "panel_set", open: true }]);
    expect(open.panelOpen).toBe(true);
    expect(builderReducer(open, { type: "panel_set", open: false }).panelOpen).toBe(false);
  });
});
