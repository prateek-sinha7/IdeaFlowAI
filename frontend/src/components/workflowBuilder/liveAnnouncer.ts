/**
 * Announcement scheduler for the Builder's polite live region (Req 14.2-14.5).
 *
 * Framework-free. It decides what is announced and when; the React live
 * region only renders the strings passed to `emit`. Only server-derived stage
 * labels and three fixed sentences can be announced, so streamed text has no
 * way in (Req 14.5).
 *
 * Stage labels are throttled to one per `STAGE_INTERVAL_MS` and the latest
 * stage wins, because a turn can make up to 60 tool calls (design: live
 * region, G-29). The applied-draft and turn-end lines are never delayed.
 */

import type { FinalTurnStatus } from "@/types/workflowBuilder";

import type { TurnView } from "./builderReducer";

export const STAGE_INTERVAL_MS = 3000;

export const DRAFT_APPLIED_MESSAGE = "Workflow updated on the canvas";

export type TurnEndKind = "finished" | "stopped" | "failed";

export const TURN_END_MESSAGES: Readonly<Record<TurnEndKind, string>> = {
  finished: "Reply finished",
  stopped: "Turn stopped",
  failed: "Turn failed",
};

export interface LiveAnnouncer {
  /** Announce a new stage label, subject to the 3 s throttle. */
  stage(label: string): void;
  /** Announce that a draft was applied to the canvas. */
  draftApplied(): void;
  /** Announce the turn end and drop any stage label still waiting. */
  turnEnded(kind: TurnEndKind): void;
  /** Cancel pending work. Call when the panel unmounts. */
  dispose(): void;
}

export function createLiveAnnouncer(
  emit: (message: string) => void,
): LiveAnnouncer {
  let lastStageAt: number | null = null;
  let lastStageLabel: string | null = null;
  let pendingLabel: string | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clearPending = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    pendingLabel = null;
  };

  const announceStage = (label: string): void => {
    lastStageAt = Date.now();
    lastStageLabel = label;
    emit(label);
  };

  const flushPending = (): void => {
    timer = null;
    const label = pendingLabel;
    pendingLabel = null;
    if (label !== null && label !== lastStageLabel) {
      announceStage(label);
    }
  };

  return {
    stage(label) {
      if (timer === null && label === lastStageLabel) {
        return;
      }
      const elapsed = lastStageAt === null ? STAGE_INTERVAL_MS : Date.now() - lastStageAt;
      if (timer === null && elapsed >= STAGE_INTERVAL_MS) {
        announceStage(label);
        return;
      }
      pendingLabel = label;
      if (timer === null) {
        timer = setTimeout(flushPending, STAGE_INTERVAL_MS - elapsed);
      }
    },
    draftApplied() {
      emit(DRAFT_APPLIED_MESSAGE);
    },
    turnEnded(kind) {
      clearPending();
      emit(TURN_END_MESSAGES[kind]);
    },
    dispose: clearPending,
  };
}

// --- Transitions -------------------------------------------------------------------------

export type LiveAnnouncement =
  | { kind: "stage"; label: string }
  | { kind: "draft" }
  | { kind: "turn_end"; end: TurnEndKind };

/** What the live region shows from the panel state at one point in time. */
export interface LiveSnapshot {
  turn: TurnView;
  /** Revision number of the draft on the canvas; 0 when none. */
  draftRevision: number;
}

/** Map a turn's final status to the end line. `completed` is a finished reply; everything else is a stop or failure. */
export function turnEndKind(status: FinalTurnStatus): TurnEndKind {
  switch (status) {
    case "completed":
      return "finished";
    case "failed":
      return "failed";
    default:
      return "stopped";
  }
}

/**
 * The announcements a state change calls for, in announcement order: the
 * applied draft, then a stage label that changed, then the turn end.
 *
 * `prev` is null on the first render. Mounting in the middle of a turn
 * announces its current stage, and the draft already on the canvas is not
 * announced. A draft counts only when a turn is running before or after the
 * change, so loading a session never announces "Workflow updated". Streamed
 * text never produces an announcement.
 */
export function announcementsBetween(
  prev: LiveSnapshot | null,
  next: LiveSnapshot,
): LiveAnnouncement[] {
  if (prev === null) {
    return next.turn.kind === "running" ? [{ kind: "stage", label: next.turn.label }] : [];
  }

  const announcements: LiveAnnouncement[] = [];
  const wasRunning = prev.turn.kind === "running";
  const isRunning = next.turn.kind === "running";

  if (next.draftRevision > prev.draftRevision && (wasRunning || isRunning)) {
    announcements.push({ kind: "draft" });
  }

  if (next.turn.kind === "running") {
    const previousLabel =
      prev.turn.kind === "running" && prev.turn.turnId === next.turn.turnId
        ? prev.turn.label
        : null;
    if (previousLabel !== next.turn.label) {
      announcements.push({ kind: "stage", label: next.turn.label });
    }
  }

  if (
    prev.turn.kind === "running" &&
    next.turn.kind === "ended" &&
    prev.turn.turnId === next.turn.turnId
  ) {
    announcements.push({ kind: "turn_end", end: turnEndKind(next.turn.status) });
  }

  return announcements;
}
