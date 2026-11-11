/**
 * Panel state reducer of the AI Workflow Builder (design 3.10.4).
 *
 * Pure: no clock, no I/O, no randomness. Callers pass `now` (ms) inside
 * `stream_event` actions. Server events and local actions are folded into one
 * `BuilderState`. The effects (REST calls, the unsaved-work prompt) belong to
 * the host, which reads `needsReload` and `draft`.
 */

import { canonicalJson } from "@/lib/canonicalManifest";
import type { WorkflowManifest } from "@/types/index";
import type {
  BuilderEvent,
  BuilderStage,
  CheckResult,
  DraftAppliedEvent,
  DraftRevisionOut,
  DraftRestoredEvent,
  ErrorEvent,
  FinalTurnStatus,
  LimitKind,
  Outcome,
  RevisionKind,
  RunningTurnSnapshot,
  SessionDetail,
  SnapshotEvent,
  StopReason,
  TargetTrust,
  ToolActivity,
  TurnStartedEvent,
  WireManifest,
} from "@/types/workflowBuilder";

// --- State model --------------------------------------------------------------------

export type SessionLoad =
  | { kind: "none" }
  | { kind: "loading"; sessionId: string }
  | { kind: "not_found"; sessionId: string }
  | { kind: "ready"; session: SessionDetail };

export type TurnOrigin = "this_tab" | "other_tab" | "rejoined";

export type ActivityLine = ToolActivity;
export type CheckLine = CheckResult;

export interface LimitWarningView {
  kind: LimitKind;
  used: number;
  limit: number;
}

export interface RunningTurnView {
  kind: "running";
  turnId: string;
  origin: TurnOrigin;
  stage: BuilderStage;
  label: string;
  /** Client clock, ms since the epoch. */
  startedAt: number;
  lastSeq: number;
  activity: ActivityLine[];
  checks: CheckLine[];
  warnings: LimitWarningView[];
  /** Filled only when `origin === "this_tab"`. */
  text: string;
  /** Filled only when `origin === "this_tab"`. */
  thinking: string;
  /** Held when `origin !== "this_tab"` until `turn_completed`. */
  pendingDraft: DraftAppliedEvent | null;
}

export type TurnView =
  | { kind: "idle" }
  | { kind: "sending"; clientMessageId: string; text: string }
  | RunningTurnView
  | {
      kind: "ended";
      turnId: string;
      status: FinalTurnStatus;
      outcome: Outcome;
      stopReason: StopReason | null;
    };

export type CanvasDraft =
  | { kind: "none" }
  | {
      kind: "applied";
      revision: number;
      manifest: WorkflowManifest;
      targetTrust: TargetTrust;
      /** Canonical JSON of the manifest: equal strings mean equal workflows. */
      fingerprint: string;
    };

export type Notice =
  | { kind: "none" }
  | { kind: "reply_in_progress_elsewhere" }
  | { kind: "deleted_elsewhere" }
  | { kind: "linked_row_changed" }
  | { kind: "model_unavailable"; fallbackModelId: string };

export interface BuilderState {
  load: SessionLoad;
  turn: TurnView;
  draft: CanvasDraft;
  notice: Notice;
  panelOpen: boolean;
  /** Turn ids this tab got back from `POST .../messages` (newest last, capped). */
  ownTurnIds: readonly string[];
  /** True when the host should `GET /sessions/{id}`; cleared by `session_loaded`. */
  needsReload: boolean;
  /**
   * The message this tab sent whose stored row has not been loaded yet. The
   * transcript shows it from `send_started` until a `session_loaded` carries the
   * user row of `turnId`, so the user's own text stays visible while the turn
   * runs and until the reload after `turn_completed`.
   */
  pendingUser: PendingUserMessage | null;
}

export interface PendingUserMessage {
  text: string;
  /** Set by `send_accepted`; `null` while the POST is in flight. */
  turnId: string | null;
}

export const INITIAL_BUILDER_STATE: BuilderState = {
  load: { kind: "none" },
  turn: { kind: "idle" },
  draft: { kind: "none" },
  notice: { kind: "none" },
  panelOpen: false,
  ownTurnIds: [],
  needsReload: false,
  pendingUser: null,
};

/** True when `session` already holds the stored user row of the pending message. */
function pendingIsStored(pending: PendingUserMessage | null, session: SessionDetail): boolean {
  if (pending === null || pending.turnId === null) {
    return false;
  }
  const turnId = pending.turnId;
  return session.messages.some((m) => m.role === "user" && m.turn_id === turnId);
}

const MAX_OWN_TURN_IDS = 20;

// --- Actions ------------------------------------------------------------------------

export type BuilderAction =
  | { type: "session_loading"; sessionId: string }
  | { type: "session_not_found"; sessionId: string }
  | { type: "session_loaded"; session: SessionDetail }
  | { type: "session_cleared" }
  | { type: "send_started"; clientMessageId: string; text: string }
  | { type: "send_accepted"; turnId: string }
  | { type: "send_failed"; reason: "conflict" | "other" }
  | { type: "stream_event"; event: BuilderEvent; now: number }
  | { type: "notice_set"; notice: Notice }
  | { type: "notice_dismissed" }
  | { type: "panel_set"; open: boolean }
  | { type: "reload_acknowledged" };

// --- Helpers ------------------------------------------------------------------------

const NO_NOTICE: Notice = { kind: "none" };

/** The one place a wire manifest becomes a `WorkflowManifest`: it must have `steps`. */
function toWorkflowManifest(wire: WireManifest): WorkflowManifest | null {
  return Array.isArray(wire.steps) ? (wire as unknown as WorkflowManifest) : null;
}

function fingerprintOf(manifest: WorkflowManifest): string {
  try {
    return canonicalJson(manifest as unknown as Record<string, unknown>);
  } catch {
    return JSON.stringify(manifest);
  }
}

function withTurn(state: BuilderState, turn: TurnView): BuilderState {
  return { ...state, turn };
}

function loadedSessionId(load: SessionLoad): string | null {
  switch (load.kind) {
    case "none":
      return null;
    case "ready":
      return load.session.id;
    default:
      return load.sessionId;
  }
}

function currentRevision(draft: CanvasDraft): number {
  return draft.kind === "applied" ? draft.revision : 0;
}

/** What is needed to put a revision on the canvas and into the cached session. */
interface DraftSource {
  revision: number;
  manifest: WireManifest;
  targetTrust: TargetTrust | null;
  kind: RevisionKind;
  changeSummary: DraftRevisionOut["change_summary"];
  launchNeeds: DraftRevisionOut["launch_needs"];
  sourceTurnId: string | null;
  createdAt: string;
}

function sourceFromApplied(event: DraftAppliedEvent): DraftSource {
  return {
    revision: event.revision,
    manifest: event.manifest,
    targetTrust: event.target_trust,
    kind: "accepted",
    changeSummary: event.change_summary,
    launchNeeds: event.launch_needs,
    sourceTurnId: event.turn_id,
    createdAt: event.ts,
  };
}

function sourceFromRestored(event: DraftRestoredEvent): DraftSource {
  return {
    revision: event.revision,
    manifest: event.manifest,
    targetTrust: null,
    kind: "undo",
    changeSummary: null,
    launchNeeds: [],
    sourceTurnId: null,
    createdAt: event.ts,
  };
}

/**
 * Put a revision on the canvas. Ignored when the manifest is malformed or the
 * revision is not newer than the one already shown (revisions only grow, undo
 * included), which also makes a duplicate delivery harmless.
 */
function commitDraft(state: BuilderState, source: DraftSource): BuilderState {
  const manifest = toWorkflowManifest(source.manifest);
  if (manifest === null || source.revision <= currentRevision(state.draft)) {
    return state;
  }
  const trust: TargetTrust =
    source.targetTrust ??
    (state.draft.kind === "applied"
      ? state.draft.targetTrust
      : state.load.kind === "ready"
        ? state.load.session.target_trust
        : "user");
  const draft: CanvasDraft = {
    kind: "applied",
    revision: source.revision,
    manifest,
    targetTrust: trust,
    fingerprint: fingerprintOf(manifest),
  };
  const load: SessionLoad =
    state.load.kind === "ready"
      ? {
          kind: "ready",
          session: {
            ...state.load.session,
            latest_draft: {
              revision: source.revision,
              kind: source.kind,
              manifest: source.manifest,
              target_trust: trust,
              change_summary: source.changeSummary,
              launch_needs: source.launchNeeds,
              source_turn_id: source.sourceTurnId,
              created_at: source.createdAt,
            },
            latest_unproposed: null,
          },
        }
      : state.load;
  return { ...state, draft, load };
}

function runningFromSnapshot(
  snapshot: RunningTurnSnapshot,
  serverTs: string,
  now: number,
): RunningTurnView {
  // Elapsed time is measured on the server clock, so client clock skew does not show.
  const elapsed = Date.parse(serverTs) - Date.parse(snapshot.started_at);
  return {
    kind: "running",
    turnId: snapshot.turn_id,
    origin: "rejoined",
    stage: snapshot.stage,
    label: snapshot.label,
    startedAt: Number.isFinite(elapsed) && elapsed >= 0 ? now - elapsed : now,
    lastSeq: snapshot.through_seq,
    activity: snapshot.activity,
    checks: snapshot.checks,
    warnings: [],
    text: "",
    thinking: "",
    pendingDraft: null,
  };
}

// --- Stream events ------------------------------------------------------------------

function applySnapshot(state: BuilderState, event: SnapshotEvent, now: number): BuilderState {
  const running = event.running_turn;
  let turn = state.turn;
  let needsReload = state.needsReload;

  if (running !== null) {
    if (turn.kind === "running" && turn.turnId === running.turn_id) {
      // Same turn after a reconnect: the snapshot's activity is a superset; text stays.
      turn = {
        ...turn,
        stage: running.stage,
        label: running.label,
        activity: running.activity,
        checks: running.checks,
        lastSeq: Math.max(turn.lastSeq, running.through_seq),
      };
    } else {
      turn = runningFromSnapshot(running, event.ts, now);
    }
  } else if (turn.kind === "running") {
    // The turn ended while the stream was down. Its outcome is only in the stored rows.
    turn = { kind: "idle" };
    needsReload = true;
  }

  if (
    state.load.kind === "ready" &&
    event.latest_revision !== null &&
    event.latest_revision > currentRevision(state.draft)
  ) {
    needsReload = true;
  }
  return { ...state, turn, needsReload };
}

function applyTurnStarted(
  state: BuilderState,
  event: TurnStartedEvent,
  now: number,
): BuilderState {
  const previous = state.turn;
  if (previous.kind === "running" && previous.turnId === event.turn_id) {
    return event.seq > previous.lastSeq
      ? withTurn(state, { ...previous, lastSeq: event.seq })
      : state;
  }
  const origin: TurnOrigin =
    previous.kind === "sending" || state.ownTurnIds.includes(event.turn_id)
      ? "this_tab"
      : "other_tab";
  const turn: RunningTurnView = {
    kind: "running",
    turnId: event.turn_id,
    origin,
    stage: "starting",
    label: "Starting",
    startedAt: now,
    lastSeq: event.seq,
    activity: [],
    checks: [],
    warnings: [],
    text: "",
    thinking: "",
    pendingDraft: null,
  };
  return {
    ...state,
    turn,
    needsReload: state.needsReload || previous.kind === "running",
  };
}

type TurnScopedEvent = Exclude<
  BuilderEvent,
  | SnapshotEvent
  | TurnStartedEvent
  | DraftRestoredEvent
  | ErrorEvent
  | { type: "session_deleted" }
  | { type: "session_revoked" }
>;

function reduceTurnEvent(state: BuilderState, event: TurnScopedEvent): BuilderState {
  const previous = state.turn;
  if (
    previous.kind !== "running" ||
    previous.turnId !== event.turn_id ||
    event.seq <= previous.lastSeq
  ) {
    return state;
  }
  const turn: RunningTurnView = { ...previous, lastSeq: event.seq };

  switch (event.type) {
    case "stage":
      return withTurn(state, { ...turn, stage: event.stage, label: event.label });
    case "thinking":
      return turn.origin === "this_tab"
        ? withTurn(state, { ...turn, thinking: turn.thinking + event.text })
        : withTurn(state, turn);
    case "text":
      return turn.origin === "this_tab"
        ? withTurn(state, { ...turn, text: turn.text + event.text })
        : withTurn(state, turn);
    case "tool_started": {
      if (turn.activity.some((line) => line.call_id === event.call_id)) {
        return withTurn(state, turn);
      }
      const line: ActivityLine = {
        call_id: event.call_id,
        tool: event.tool,
        kind: event.kind,
        label: event.label,
        status: "running",
        duration_ms: null,
        command: event.command,
        exit_code: null,
        summary: null,
      };
      return withTurn(state, { ...turn, activity: [...turn.activity, line] });
    }
    case "tool_finished":
      return withTurn(state, {
        ...turn,
        activity: turn.activity.map((line) =>
          line.call_id === event.call_id
            ? {
                ...line,
                status: event.status,
                duration_ms: event.duration_ms,
                summary: event.summary,
              }
            : line,
        ),
      });
    case "check_result": {
      const check: CheckLine = {
        source: event.source,
        verdict: event.verdict,
        errors: event.errors,
        warnings: event.warnings,
        attempt: event.attempt,
        attempts_left: event.attempts_left,
      };
      return withTurn(state, { ...turn, checks: [...turn.checks, check] });
    }
    case "limit_warning": {
      const warning: LimitWarningView = {
        kind: event.kind,
        used: event.used,
        limit: event.limit,
      };
      return withTurn(state, {
        ...turn,
        warnings: [...turn.warnings.filter((w) => w.kind !== event.kind), warning],
      });
    }
    case "draft_applied":
      if (turn.origin === "this_tab") {
        return commitDraft(withTurn(state, turn), sourceFromApplied(event));
      }
      return withTurn(state, { ...turn, pendingDraft: event });
    case "turn_completed": {
      const held = turn.pendingDraft;
      const base: BuilderState = {
        ...state,
        needsReload: true,
        notice:
          state.notice.kind === "reply_in_progress_elsewhere" ? NO_NOTICE : state.notice,
        turn: {
          kind: "ended",
          turnId: turn.turnId,
          status: event.status,
          outcome: event.outcome,
          stopReason: event.stop_reason,
        },
      };
      return held === null ? base : commitDraft(base, sourceFromApplied(held));
    }
    default: {
      const unreachable: never = event;
      return unreachable;
    }
  }
}

function reduceStreamEvent(state: BuilderState, event: BuilderEvent, now: number): BuilderState {
  switch (event.type) {
    case "snapshot":
      return applySnapshot(state, event, now);
    case "turn_started":
      return applyTurnStarted(state, event, now);
    case "draft_restored":
      return commitDraft(state, sourceFromRestored(event));
    case "session_deleted": {
      const id = loadedSessionId(state.load);
      return {
        ...state,
        load: id === null ? state.load : { kind: "not_found", sessionId: id },
        turn: { kind: "idle" },
        notice: { kind: "deleted_elsewhere" },
      };
    }
    case "session_revoked":
      // The hook expires the session; nothing in the panel state changes.
      return state;
    case "error": {
      // The turn ends with its own `turn_completed`; the stored message carries the error.
      if (event.turn_id === null || event.seq === null) {
        return state;
      }
      const turn = state.turn;
      return turn.kind === "running" && turn.turnId === event.turn_id && event.seq > turn.lastSeq
        ? withTurn(state, { ...turn, lastSeq: event.seq })
        : state;
    }
    default:
      return reduceTurnEvent(state, event);
  }
}

// --- Reducer ------------------------------------------------------------------------

export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case "session_loading":
      return {
        ...INITIAL_BUILDER_STATE,
        load: { kind: "loading", sessionId: action.sessionId },
        panelOpen: state.panelOpen,
      };
    case "session_not_found":
      return { ...state, load: { kind: "not_found", sessionId: action.sessionId } };
    case "session_cleared":
      return { ...INITIAL_BUILDER_STATE, panelOpen: state.panelOpen };
    case "session_loaded": {
      const knownId = loadedSessionId(state.load);
      if (knownId !== null && knownId !== action.session.id) {
        return state;
      }
      const { latest_draft: latest } = action.session;
      const next: BuilderState = {
        ...state,
        load: { kind: "ready", session: action.session },
        needsReload: false,
        pendingUser: pendingIsStored(state.pendingUser, action.session) ? null : state.pendingUser,
        notice:
          action.session.linked_row_changed && state.notice.kind === "none"
            ? { kind: "linked_row_changed" }
            : state.notice,
      };
      // A seed is the starting manifest, which the canvas already shows.
      if (latest === null || latest.kind === "seed") {
        return next;
      }
      return commitDraft(next, {
        revision: latest.revision,
        manifest: latest.manifest,
        targetTrust: latest.target_trust ?? action.session.target_trust,
        kind: latest.kind,
        changeSummary: latest.change_summary,
        launchNeeds: latest.launch_needs,
        sourceTurnId: latest.source_turn_id,
        createdAt: latest.created_at,
      });
    }
    case "send_started":
      if (state.turn.kind === "sending" || state.turn.kind === "running") {
        return state;
      }
      return {
        ...state,
        turn: { kind: "sending", clientMessageId: action.clientMessageId, text: action.text },
        // A retry sends no new text, so the stored message stays the only bubble.
        pendingUser: action.text === "" ? null : { text: action.text, turnId: null },
        notice: state.notice.kind === "reply_in_progress_elsewhere" ? NO_NOTICE : state.notice,
      };
    case "send_accepted":
      return {
        ...state,
        pendingUser:
          state.pendingUser !== null && state.pendingUser.turnId === null
            ? { ...state.pendingUser, turnId: action.turnId }
            : state.pendingUser,
        ownTurnIds: [...state.ownTurnIds.filter((id) => id !== action.turnId), action.turnId].slice(
          -MAX_OWN_TURN_IDS,
        ),
      };
    case "send_failed": {
      const turn = state.turn;
      // The message was not stored, so nothing may stay on screen as sent.
      const unsent: BuilderState =
        state.pendingUser !== null && state.pendingUser.turnId === null
          ? { ...state, pendingUser: null }
          : state;
      if (action.reason === "other") {
        return turn.kind === "sending" ? withTurn(unsent, { kind: "idle" }) : unsent;
      }
      const notice: Notice = { kind: "reply_in_progress_elsewhere" };
      if (turn.kind === "sending") {
        return { ...unsent, turn: { kind: "idle" }, notice };
      }
      // Another tab's turn_started arrived while this tab was sending and was taken for
      // our own. The 409 proves it is not: drop the origin and anything accumulated.
      if (
        turn.kind === "running" &&
        turn.origin === "this_tab" &&
        !state.ownTurnIds.includes(turn.turnId)
      ) {
        return {
          ...unsent,
          turn: { ...turn, origin: "other_tab", text: "", thinking: "" },
          notice,
        };
      }
      return { ...unsent, notice };
    }
    case "stream_event":
      return reduceStreamEvent(state, action.event, action.now);
    case "notice_set":
      return { ...state, notice: action.notice };
    case "notice_dismissed":
      return { ...state, notice: NO_NOTICE };
    case "panel_set":
      return { ...state, panelOpen: action.open };
    case "reload_acknowledged":
      return { ...state, needsReload: false };
    default: {
      const unreachable: never = action;
      return unreachable;
    }
  }
}
