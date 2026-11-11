"use client";

/**
 * BuilderTranscript: the messages of a session in the order they were created,
 * plus the turn in progress (Req 4.1, 5.1, 5.2, 16.8, 16.9, 17.10).
 *
 * Laid out like the run chat: the user's messages in the shared brand bubble on
 * the right, the builder's replies beside the shared assistant mark.
 *
 * Stored messages render through `BuilderMessage`. An ended assistant message
 * shows its stored activity as one collapsed line above it. A running turn
 * renders at the end of the list, or in place of its stored running row after a
 * reload. Its text and thinking appear only in the tab that sent the message
 * (`origin === "this_tab"`). Other tabs and reloaded tabs show "Still working"
 * with the activity so far (Req 16.9).
 *
 * The transcript is not a live region. Streamed text stays out of the polite
 * live region (Req 14.5), so this element must not use `role="log"`, which
 * implies `aria-live`.
 */

import type { ReactNode } from "react";

import { AssistantMark } from "@/components/chat/AssistantMark";
import { USER_BUBBLE_CLASS, USER_BUBBLE_TEXT_CLASS } from "@/components/chat/chatStyles";
import type { DraftRevisionOut, TranscriptMessage } from "@/types/workflowBuilder";

import { BuilderMessage } from "./BuilderMessage";
import { ActivityList, BuilderProgress } from "./BuilderProgress";
import type { RunningTurnView, TurnView } from "./builderReducer";
import { orderedStepsOf, undoTargetMessageId } from "./builderSelectors";

export interface BuilderTranscriptProps {
  messages: readonly TranscriptMessage[];
  /** Draft revisions the transcript can show change summaries for. */
  revisions: readonly DraftRevisionOut[];
  turn: TurnView;
  /**
   * The text this tab sent whose stored row has not loaded yet (reducer
   * `pendingUser`). It stays on screen while the turn runs. When omitted, only
   * an in-flight send shows its text.
   */
  pendingUserText?: string | null;
  /**
   * True while the first message of a new conversation waits for the
   * conversation to be created and its stream to open. The pending message then
   * shows "Sending" although no send is in flight yet.
   */
  starting?: boolean;
  /** Disables Retry, Continue and Undo, for example while a turn runs. */
  actionsDisabled?: boolean;
  onRetry?: () => void;
  onContinue?: () => void;
  onUndo?: () => void;
}

const BUBBLE_CLASS = `ml-auto max-w-[86%] break-words ${USER_BUBBLE_CLASS} ${USER_BUBBLE_TEXT_CLASS}`;

/** A builder reply's row: the assistant mark, then the reply's content. */
function ReplyRow({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-w-0 gap-[9px]">
      <div className="flex-none pt-px">
        <AssistantMark />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">{children}</div>
    </div>
  );
}

// --- Live parts -----------------------------------------------------------------------

/** The turn in progress. Its steps appear in the order they happened. */
function LiveReply({ turn }: { turn: RunningTurnView }) {
  const isOwnTab = turn.origin === "this_tab";
  // Text and thinking reach only the tab that sent the message. Other tabs see tool calls and checks.
  const steps = isOwnTab
    ? turn.steps
    : turn.steps.filter((step) => step.kind === "tools" || step.kind === "check");
  return (
    <article aria-label="Builder reply in progress" className="min-w-0">
      <ReplyRow>
        <BuilderProgress
          mode="live"
          label={turn.label}
          startedAt={turn.startedAt}
          activity={turn.activity}
          steps={steps}
          warnings={turn.warnings}
        />
        {isOwnTab ? null : (
          <p className="font-sans text-[12px] font-semibold text-ink-700">Still working</p>
        )}
      </ReplyRow>
    </article>
  );
}

/** A stored assistant row still marked running. Shows the stored activity, or the live view when this tab has it. */
function StoredRunningReply({
  message,
  live,
}: {
  message: TranscriptMessage;
  live: RunningTurnView | null;
}) {
  if (live !== null) {
    return <LiveReply turn={live} />;
  }
  return (
    <article aria-label="Builder reply in progress" className="min-w-0">
      <ReplyRow>
        <p className="font-sans text-[12px] font-semibold text-ink-700">Still working</p>
        <ActivityList activity={message.activity} />
      </ReplyRow>
    </article>
  );
}

/** The user's message until its stored row loads; "Sending" while the POST is in flight. */
function PendingUserMessage({ text, sending }: { text: string; sending: boolean }) {
  return (
    <div className="flex min-w-0 flex-col items-end gap-1">
      <article aria-label="Your message" className={BUBBLE_CLASS}>
        {text}
      </article>
      {sending ? <p className="font-sans text-[11px] text-ink-400">Sending</p> : null}
    </div>
  );
}

// --- Transcript ------------------------------------------------------------------------

export function BuilderTranscript({
  messages,
  revisions,
  turn,
  pendingUserText,
  starting = false,
  actionsDisabled = false,
  onRetry,
  onContinue,
  onUndo,
}: BuilderTranscriptProps) {
  const ordered = [...messages].sort((a, b) => a.seq - b.seq);
  const pendingText =
    pendingUserText !== undefined
      ? (pendingUserText ?? "")
      : turn.kind === "sending"
        ? turn.text
        : "";
  const undoId = undoTargetMessageId(ordered, revisions);
  const liveTurn = turn.kind === "running" ? turn : null;
  const liveRowStored =
    liveTurn !== null &&
    ordered.some((message) => message.role === "assistant" && message.turn_id === liveTurn.turnId);

  return (
    <section aria-label="Conversation" className="flex min-w-0 flex-col gap-5">
      {ordered.length === 0 && turn.kind === "idle" && pendingText === "" ? (
        <p className="font-sans text-[12px] text-ink-500">Describe the workflow you want to build.</p>
      ) : null}

      {ordered.map((message) => {
        if (message.role === "user") {
          return <BuilderMessage key={message.id} message={message} />;
        }

        if (message.status === "running") {
          const live = liveTurn !== null && liveTurn.turnId === message.turn_id ? liveTurn : null;
          return <StoredRunningReply key={message.id} message={message} live={live} />;
        }

        const draft =
          message.revision === null
            ? null
            : (revisions.find((entry) => entry.revision === message.revision) ?? null);
        const stopped = message.status === "timed_out" || message.status === "interrupted";
        const summary = message.activity_summary;
        // Stored steps put thinking, tool calls and checks in the order they happened.
        // A turn without them keeps the older layout (a flat list, a separate Thinking block).
        const orderedSteps = orderedStepsOf(message);
        return (
          <ReplyRow key={message.id}>
            {summary !== null && summary.actions > 0 ? (
              <BuilderProgress
                mode="ended"
                summary={summary}
                activity={message.activity}
                checks={[]}
                steps={orderedSteps}
              />
            ) : null}
            <BuilderMessage
              message={message}
              hideThinking={orderedSteps !== null}
              draft={draft}
              actionsDisabled={actionsDisabled}
              onRetry={message.status === "failed" ? onRetry : undefined}
              onContinue={stopped ? onContinue : undefined}
              onUndo={message.id === undoId ? onUndo : undefined}
            />
          </ReplyRow>
        );
      })}

      {/* A retry sends no new text, so there is no bubble: the stored message stays the only one. */}
      {pendingText !== "" ? (
        <PendingUserMessage
          text={pendingText}
          sending={turn.kind === "sending" || (starting && turn.kind !== "running")}
        />
      ) : null}

      {liveTurn !== null && !liveRowStored ? <LiveReply turn={liveTurn} /> : null}
    </section>
  );
}

export default BuilderTranscript;
