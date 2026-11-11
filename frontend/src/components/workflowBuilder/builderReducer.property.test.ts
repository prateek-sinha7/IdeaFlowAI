import fc from "fast-check";
import { describe, expect, it } from "vitest";

import type {
  BuilderEvent,
  BuilderStage,
  ChangeSummary,
  FinalTurnStatus,
  LimitKind,
  RevisionKind,
  SessionDetail,
  ToolFinishStatus,
  ToolStatus,
  WireManifest,
} from "@/types/workflowBuilder";

import {
  builderReducer,
  INITIAL_BUILDER_STATE,
  type BuilderAction,
  type BuilderState,
  type TurnStep,
} from "./builderReducer";

// Feature: ai-workflow-builder, Property 34: The panel reducer is consistent
// **Validates: Requirements 5.1, 5.2, 7.10, 17.2, 17.9**

// Fixed seed keeps failures reproducible.
const PROPERTY_OPTIONS = { seed: 20260512, numRuns: 200 } as const;

const TS = "2026-01-01T00:00:00Z";
const NOW = 1000;
const SESSION_ID = "s1";

const CHANGE_SUMMARY: ChangeSummary = {
  added: [],
  removed: [],
  reordered: false,
  gates_changed: [],
  validators_changed: [],
  models_changed: [],
  prompts_changed: 0,
};

const STAGES: readonly BuilderStage[] = [
  "starting",
  "thinking",
  "reading",
  "looking_up",
  "writing",
  "checking",
  "platform_check",
  "applying",
  "responding",
];
const FINISH_STATUSES: readonly ToolFinishStatus[] = ["ok", "error", "refused", "timed_out"];
const FINAL_STATUSES: readonly FinalTurnStatus[] = [
  "completed",
  "failed",
  "cancelled",
  "timed_out",
  "interrupted",
];

// --- Generators ---------------------------------------------------------------------

// Small pools make repeats, stale seqs and clashing ids likely.
const turnId = fc.constantFrom("t1", "t2", "t3");
const callId = fc.constantFrom("c1", "c2", "c3");
const seqArb = fc.integer({ min: 0, max: 8 });
const revisionArb = fc.integer({ min: 1, max: 6 });
const deltaText = fc.string({ maxLength: 6 });
// The last two are rejected by the reducer (no `steps` array): the canvas must not change.
const manifestArb = fc.constantFrom<WireManifest>(
  { steps: [{ id: "a" }] },
  { steps: [{ id: "a" }, { id: "b" }] },
  { steps: "not-a-list" },
  {},
);

function turnEvent(turn_id: string, seq: number): fc.Arbitrary<BuilderEvent> {
  const base = { ts: TS, turn_id, seq };
  return fc.oneof(
    {
      weight: 3,
      arbitrary: deltaText.map((text): BuilderEvent => ({ ...base, type: "text", text })),
    },
    {
      weight: 3,
      arbitrary: deltaText.map((text): BuilderEvent => ({ ...base, type: "thinking", text })),
    },
    {
      weight: 1,
      arbitrary: fc
        .constantFrom(...STAGES)
        .map((stage): BuilderEvent => ({ ...base, type: "stage", stage, label: stage })),
    },
    {
      weight: 2,
      arbitrary: callId.map(
        (call_id): BuilderEvent => ({
          ...base,
          type: "tool_started",
          call_id,
          tool: "read_file",
          kind: "read",
          label: `Read ${call_id}`,
          command: null,
        }),
      ),
    },
    {
      weight: 2,
      arbitrary: fc.tuple(callId, fc.constantFrom(...FINISH_STATUSES)).map(
        ([call_id, status]): BuilderEvent => ({
          ...base,
          type: "tool_finished",
          call_id,
          status,
          duration_ms: 5,
          summary: "done",
        }),
      ),
    },
    {
      weight: 1,
      arbitrary: fc.constant<BuilderEvent>({
        ...base,
        type: "check_result",
        source: "skill_validator",
        verdict: "valid",
        errors: 0,
        warnings: 0,
        attempt: null,
        attempts_left: null,
      }),
    },
    {
      weight: 1,
      arbitrary: fc
        .constantFrom<LimitKind>("time", "tool_calls", "tokens")
        .map((kind): BuilderEvent => ({ ...base, type: "limit_warning", kind, used: 1, limit: 2 })),
    },
    {
      weight: 2,
      arbitrary: fc.tuple(revisionArb, manifestArb).map(
        ([revision, manifest]): BuilderEvent => ({
          ...base,
          type: "draft_applied",
          revision,
          target_trust: "user",
          change_summary: CHANGE_SUMMARY,
          launch_needs: [],
          manifest,
        }),
      ),
    },
    {
      weight: 1,
      arbitrary: fc.constantFrom(...FINAL_STATUSES).map(
        (status): BuilderEvent => ({
          ...base,
          type: "turn_completed",
          status,
          outcome: "draft",
          stop_reason: null,
          message_id: "m2",
          revision: null,
          usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, summary: null },
        }),
      ),
    },
  );
}

function turnStarted(turn_id: string, seq: number): BuilderEvent {
  return {
    type: "turn_started",
    ts: TS,
    turn_id,
    seq,
    message_id: "m1",
    model_id: "x",
    effort: null,
    skill_hash: "h",
  };
}

function errorEvent(turn_id: string | null, seq: number | null): BuilderEvent {
  return {
    type: "error",
    ts: TS,
    turn_id,
    seq,
    code: "boom",
    message: "generic",
    retryable: false,
  };
}

function snapshotEvent(
  running: { turn_id: string; through_seq: number; stage: BuilderStage } | null,
  latestRevision: number | null,
): BuilderEvent {
  return {
    type: "snapshot",
    ts: TS,
    state: running === null ? "idle" : "running",
    latest_message_id: null,
    latest_revision: latestRevision,
    latest_unproposed_revision: null,
    running_turn:
      running === null
        ? null
        : {
            turn_id: running.turn_id,
            message_id: "m9",
            stage: running.stage,
            label: running.stage,
            started_at: TS,
            through_seq: running.through_seq,
            activity: [],
            checks: [],
          },
  };
}

function sessionWith(
  latest: { revision: number; kind: RevisionKind; manifest: WireManifest } | null,
): SessionDetail {
  return {
    id: SESSION_ID,
    title: "t",
    mode: "create",
    workflow_id: null,
    model_id: "m",
    effort: null,
    running: false,
    created_at: TS,
    updated_at: TS,
    target_trust: "user",
    skill_hash: "h",
    messages: [],
    latest_draft:
      latest === null
        ? null
        : {
            ...latest,
            target_trust: null,
            change_summary: null,
            launch_needs: [],
            source_turn_id: null,
            created_at: TS,
          },
    latest_unproposed: null,
    running_turn: null,
    linked_row_changed: false,
  };
}

function ev(event: BuilderEvent): BuilderAction {
  return { type: "stream_event", event, now: NOW };
}

/** The kind and text of each thinking and text step, in order. */
function textSteps(steps: readonly TurnStep[]): { kind: "thinking" | "text"; text: string }[] {
  return steps.flatMap((step) =>
    step.kind === "thinking" || step.kind === "text" ? [{ kind: step.kind, text: step.text }] : [],
  );
}

function run(actions: readonly BuilderAction[], from: BuilderState = INITIAL_BUILDER_STATE) {
  return actions.reduce(builderReducer, from);
}

/** Any stream event, turn-scoped or not, with ids and seqs drawn from small pools. */
const anyEvent: fc.Arbitrary<BuilderEvent> = fc.oneof(
  {
    weight: 8,
    arbitrary: fc.tuple(turnId, seqArb).chain(([id, seq]) => turnEvent(id, seq)),
  },
  {
    weight: 4,
    arbitrary: fc
      .tuple(turnId, fc.integer({ min: 1, max: 8 }))
      .map(([id, seq]) => turnStarted(id, seq)),
  },
  {
    weight: 2,
    arbitrary: fc
      .tuple(
        fc.option(
          fc.record({
            turn_id: turnId,
            through_seq: seqArb,
            stage: fc.constantFrom(...STAGES),
          }),
          { nil: null },
        ),
        fc.option(revisionArb, { nil: null }),
      )
      .map(([running, latest]) => snapshotEvent(running, latest)),
  },
  {
    weight: 2,
    arbitrary: fc
      .tuple(revisionArb, manifestArb)
      .map(([revision, manifest]): BuilderEvent => ({
        type: "draft_restored",
        ts: TS,
        revision,
        manifest,
      })),
  },
  {
    weight: 1,
    arbitrary: fc
      .tuple(fc.option(turnId, { nil: null }), seqArb)
      .map(([id, seq]) => errorEvent(id, id === null ? null : seq)),
  },
  { weight: 1, arbitrary: fc.constant<BuilderEvent>({ type: "session_deleted", ts: TS }) },
  {
    weight: 1,
    arbitrary: fc.constant<BuilderEvent>({
      type: "session_revoked",
      ts: TS,
      session_id: SESSION_ID,
      reason: "r",
    }),
  },
);

const anyAction: fc.Arbitrary<BuilderAction> = fc.oneof(
  { weight: 12, arbitrary: anyEvent.map(ev) },
  {
    weight: 2,
    arbitrary: fc.constant<BuilderAction>({ type: "session_loading", sessionId: SESSION_ID }),
  },
  {
    weight: 1,
    arbitrary: fc.constant<BuilderAction>({ type: "session_not_found", sessionId: SESSION_ID }),
  },
  {
    weight: 2,
    arbitrary: fc
      .option(
        fc.record({
          revision: revisionArb,
          kind: fc.constantFrom<RevisionKind>("seed", "accepted", "undo", "unproposed"),
          manifest: manifestArb,
        }),
        { nil: null },
      )
      .map((latest): BuilderAction => ({ type: "session_loaded", session: sessionWith(latest) })),
  },
  { weight: 1, arbitrary: fc.constant<BuilderAction>({ type: "session_cleared" }) },
  {
    weight: 3,
    arbitrary: fc
      .string({ minLength: 1, maxLength: 4 })
      .map((text): BuilderAction => ({ type: "send_started", clientMessageId: "c", text })),
  },
  {
    weight: 2,
    arbitrary: turnId.map((id): BuilderAction => ({ type: "send_accepted", turnId: id })),
  },
  {
    weight: 2,
    arbitrary: fc
      .constantFrom<"conflict" | "other">("conflict", "other")
      .map((reason): BuilderAction => ({ type: "send_failed", reason })),
  },
  {
    weight: 1,
    arbitrary: fc.constant<BuilderAction>({
      type: "notice_set",
      notice: { kind: "linked_row_changed" },
    }),
  },
  { weight: 1, arbitrary: fc.constant<BuilderAction>({ type: "notice_dismissed" }) },
  { weight: 1, arbitrary: fc.boolean().map((open): BuilderAction => ({ type: "panel_set", open })) },
  { weight: 1, arbitrary: fc.constant<BuilderAction>({ type: "reload_acknowledged" }) },
);

// --- Properties ---------------------------------------------------------------------

describe("builderReducer properties (Property 34)", () => {
  it("accumulates text and thinking deltas only for a sending-tab turn", () => {
    type Origin = "sending" | "own_id" | "other_tab" | "rejoined";
    const delta = fc.record({
      kind: fc.constantFrom("text" as const, "thinking" as const, "stage" as const),
      text: deltaText,
      // Negative steps replay an old seq, zero repeats the last one.
      step: fc.integer({ min: -3, max: 4 }),
    });

    fc.assert(
      fc.property(
        fc.constantFrom<Origin>("sending", "own_id", "other_tab", "rejoined"),
        fc.integer({ min: 0, max: 5 }),
        fc.array(delta, { maxLength: 30 }),
        (origin, throughSeq, deltas) => {
          const setup: BuilderAction[] =
            origin === "sending"
              ? [{ type: "send_started", clientMessageId: "c", text: "hi" }, ev(turnStarted("t1", 1))]
              : origin === "own_id"
                ? [{ type: "send_accepted", turnId: "t1" }, ev(turnStarted("t1", 1))]
                : origin === "other_tab"
                  ? [ev(turnStarted("t1", 1))]
                  : [
                      ev(
                        snapshotEvent(
                          { turn_id: "t1", through_seq: throughSeq, stage: "reading" },
                          null,
                        ),
                      ),
                    ];
          let last = origin === "rejoined" ? throughSeq : 1;
          let cursor = last;
          const expectedSteps: { kind: "thinking" | "text"; text: string }[] = [];
          const actions: BuilderAction[] = [];
          for (const item of deltas) {
            cursor = Math.max(0, cursor + item.step);
            const base = { ts: TS, turn_id: "t1", seq: cursor };
            if (item.kind === "text") {
              actions.push(ev({ ...base, type: "text", text: item.text }));
            } else if (item.kind === "thinking") {
              actions.push(ev({ ...base, type: "thinking", text: item.text }));
            } else {
              actions.push(ev({ ...base, type: "stage", stage: "writing", label: "Writing" }));
            }
            if (cursor > last) {
              last = cursor;
              if ((item.kind === "text" || item.kind === "thinking") && item.text !== "") {
                const tail = expectedSteps[expectedSteps.length - 1];
                if (tail !== undefined && tail.kind === item.kind) {
                  tail.text += item.text;
                } else {
                  expectedSteps.push({ kind: item.kind, text: item.text });
                }
              }
            }
          }

          const state = run([...setup, ...actions]);
          const sendsHere = origin === "sending" || origin === "own_id";
          expect(state.turn.kind).toBe("running");
          if (state.turn.kind !== "running") return;
          expect(state.turn.origin).toBe(
            sendsHere ? "this_tab" : origin === "other_tab" ? "other_tab" : "rejoined",
          );
          expect(textSteps(state.turn.steps)).toEqual(sendsHere ? expectedSteps : []);
          expect(state.turn.lastSeq).toBe(last);
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("changes nothing for an event at or below the last applied seq", () => {
    const prefixEvent = fc.integer({ min: 1, max: 8 }).chain((seq) => turnEvent("t1", seq));
    const staleCandidate: fc.Arbitrary<BuilderEvent> = fc.oneof(
      { weight: 6, arbitrary: turnEvent("t1", 0) },
      { weight: 1, arbitrary: fc.constant(turnStarted("t1", 0)) },
      { weight: 1, arbitrary: fc.constant(errorEvent("t1", 0)) },
    );

    fc.assert(
      fc.property(
        fc.boolean(),
        fc.array(prefixEvent, { maxLength: 20 }),
        fc.nat({ max: 20 }),
        staleCandidate,
        (sending, prefix, back, candidate) => {
          const state = run([
            ...(sending
              ? ([{ type: "send_started", clientMessageId: "c", text: "hi" }] as BuilderAction[])
              : []),
            ev(turnStarted("t1", 1)),
            ...prefix.map(ev),
          ]);
          fc.pre(state.turn.kind === "running");
          if (state.turn.kind !== "running") return;

          const seq = state.turn.lastSeq - (back % (state.turn.lastSeq + 1));
          const stale = { ...candidate, seq } as BuilderEvent;
          expect(builderReducer(state, ev(stale))).toEqual(state);
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("holds a draft in a watching tab until turn_completed, then shows the last one", () => {
    const item = fc.record({
      revision: revisionArb,
      isDraft: fc.boolean(),
      gap: fc.integer({ min: 0, max: 3 }),
    });

    fc.assert(
      fc.property(
        fc.constantFrom("other_tab" as const, "rejoined" as const),
        fc.array(item, { maxLength: 15 }),
        (origin, items) => {
          const setup =
            origin === "other_tab"
              ? ev(turnStarted("t1", 1))
              : ev(snapshotEvent({ turn_id: "t1", through_seq: 1, stage: "reading" }, null));
          let state = run([setup]);
          let seq = 1;
          let last = 1;
          let heldRevision: number | null = null;

          for (const it of items) {
            seq = Math.max(0, seq + it.gap - 1);
            const base = { ts: TS, turn_id: "t1", seq };
            const event: BuilderEvent = it.isDraft
              ? {
                  ...base,
                  type: "draft_applied",
                  revision: it.revision,
                  target_trust: "user",
                  change_summary: CHANGE_SUMMARY,
                  launch_needs: [],
                  manifest: { steps: [{ id: "a" }] },
                }
              : { ...base, type: "text", text: "x" };
            state = builderReducer(state, ev(event));
            if (seq > last) {
              last = seq;
              if (it.isDraft) heldRevision = it.revision;
            }
            expect(state.draft.kind).toBe("none");
          }

          state = builderReducer(
            state,
            ev({
              ts: TS,
              turn_id: "t1",
              seq: last + 1,
              type: "turn_completed",
              status: "completed",
              outcome: "draft",
              stop_reason: null,
              message_id: "m2",
              revision: heldRevision,
              usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, summary: null },
            }),
          );
          expect(state.turn.kind).toBe("ended");
          if (heldRevision === null) {
            expect(state.draft.kind).toBe("none");
          } else {
            expect(state.draft).toMatchObject({ kind: "applied", revision: heldRevision });
          }
        },
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("keeps one activity line per call_id with its latest status", () => {
    const item = fc.record({
      kind: fc.constantFrom("start" as const, "finish" as const),
      callId,
      status: fc.constantFrom(...FINISH_STATUSES),
      gap: fc.integer({ min: 1, max: 3 }),
    });

    fc.assert(
      fc.property(fc.array(item, { maxLength: 40 }), (items) => {
        const expected = new Map<string, ToolStatus>();
        const actions: BuilderAction[] = [ev(turnStarted("t1", 1))];
        let seq = 1;
        for (const it of items) {
          seq += it.gap;
          const base = { ts: TS, turn_id: "t1", seq };
          if (it.kind === "start") {
            actions.push(
              ev({
                ...base,
                type: "tool_started",
                call_id: it.callId,
                tool: "read_file",
                kind: "read",
                label: `Read ${it.callId}`,
                command: null,
              }),
            );
            if (!expected.has(it.callId)) expected.set(it.callId, "running");
          } else {
            actions.push(
              ev({
                ...base,
                type: "tool_finished",
                call_id: it.callId,
                status: it.status,
                duration_ms: 5,
                summary: "done",
              }),
            );
            // A finish for a call that never started has no line to update.
            if (expected.has(it.callId)) expected.set(it.callId, it.status);
          }
        }

        const state = run(actions);
        expect(state.turn.kind).toBe("running");
        if (state.turn.kind !== "running") return;
        expect(state.turn.activity.map((line) => [line.call_id, line.status])).toEqual([
          ...expected,
        ]);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("moves the canvas draft only through draft_applied, draft_restored or a session load", () => {
    fc.assert(
      fc.property(fc.array(anyAction, { minLength: 1, maxLength: 40 }), (actions) => {
        const seen = new Set<number>();
        let state = INITIAL_BUILDER_STATE;

        for (const action of actions) {
          const before = state;
          state = builderReducer(before, action);

          // Revisions that may legitimately reach the canvas.
          if (action.type === "stream_event") {
            const e = action.event;
            if (e.type === "draft_applied" || e.type === "draft_restored") seen.add(e.revision);
          }
          if (action.type === "session_loaded" && action.session.latest_draft !== null) {
            seen.add(action.session.latest_draft.revision);
          }

          const resets = action.type === "session_loading" || action.type === "session_cleared";
          const eventType = action.type === "stream_event" ? action.event.type : null;
          const mayMoveDraft =
            resets ||
            action.type === "session_loaded" ||
            eventType === "draft_applied" ||
            eventType === "draft_restored" ||
            eventType === "turn_completed";
          if (!mayMoveDraft) {
            expect(state.draft).toEqual(before.draft);
          }

          if (state.draft.kind === "applied") {
            expect(seen.has(state.draft.revision)).toBe(true);
            if (!resets && before.draft.kind === "applied") {
              expect(state.draft.revision).toBeGreaterThanOrEqual(before.draft.revision);
            }
          }

          if (action.type === "stream_event" && action.event.type === "draft_applied") {
            // Applied at once only in the sending tab, for the running turn's next seq.
            const turn = before.turn;
            const live =
              turn.kind === "running" &&
              turn.origin === "this_tab" &&
              turn.turnId === action.event.turn_id &&
              action.event.seq > turn.lastSeq;
            if (!live) expect(state.draft).toEqual(before.draft);
          }

          if (eventType === "turn_completed" && state.draft !== before.draft) {
            // A draft moves on completion only when it was held for this turn.
            const turn = before.turn;
            expect(turn.kind).toBe("running");
            if (turn.kind === "running" && state.draft.kind === "applied") {
              expect(turn.pendingDraft).not.toBeNull();
              expect(state.draft.revision).toBe(turn.pendingDraft?.revision);
            }
          }
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("keeps the turn view well formed after any action sequence", () => {
    fc.assert(
      fc.property(fc.array(anyAction, { minLength: 1, maxLength: 40 }), (actions) => {
        let state = INITIAL_BUILDER_STATE;
        for (const action of actions) {
          const before = state;
          state = builderReducer(before, action);
          const turn = state.turn;
          if (turn.kind !== "running") continue;

          const ids = turn.activity.map((line) => line.call_id);
          expect(new Set(ids).size).toBe(ids.length);
          if (turn.origin !== "this_tab") {
            expect(
              turn.steps.filter((step) => step.kind === "thinking" || step.kind === "text"),
            ).toEqual([]);
          }
          if (before.turn.kind === "running" && before.turn.turnId === turn.turnId) {
            expect(turn.lastSeq).toBeGreaterThanOrEqual(before.turn.lastSeq);
          }
        }
      }),
      PROPERTY_OPTIONS,
    );
  });
});
